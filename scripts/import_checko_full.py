import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import async_session
from backend.models import Startup, ExternalData, StartupFinancial
from parsers.checko_parser import CheckoParser
import config
import logging
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def parse_all():
    logger.info("Starting full Checko parsing for all startups...")
    
    # Initialize parser with config keys
    api_keys = getattr(config, 'CHECKO_API_KEYS', os.environ.get('CHECKO_API_KEY'))
    if not api_keys:
        logger.error("No Checko API keys found. Exiting.")
        return
        
    parser = CheckoParser(api_key=api_keys)
    
    async with async_session() as session:
        # Get all startups with an INN
        stmt = select(Startup).where(Startup.inn != None, Startup.inn != "")
        startups = (await session.execute(stmt)).scalars().all()
        
        logger.info(f"Found {len(startups)} startups with INN.")
        
        # Check which ones already have Checko data
        stmt_ext = select(ExternalData.startup_id).where(ExternalData.source == "checko")
        already_parsed = set((await session.execute(stmt_ext)).scalars().all())
        
        to_parse = [s for s in startups if s.id not in already_parsed]
        logger.info(f"Startups remaining to parse: {len(to_parse)}")
        
        to_parse_tuples = [(s.id, str(s.inn).strip()) for s in to_parse]
        
        if not to_parse_tuples:
            logger.info("All startups already have Checko data.")
            await parser.close()
            return
            
        count = 0
        for startup_id, inn in to_parse_tuples:
            count += 1
            logger.info(f"[{count}/{len(to_parse_tuples)}] Parsing INN: {inn} (ID: {startup_id})")
            
            try:
                # 1. Запрос финансов
                data = await parser.fetch(inn=inn)
                if not data:
                    logger.warning(f"No Checko data returned for INN {inn}")
                    continue
                
                # 2. Запрос расширенной информации о компании (учредители, налоги, риски)
                company_data = await parser.fetch_company(inn=inn)
                if company_data:
                    data["company_details"] = company_data
                await asyncio.sleep(0.3)

                # 3. Запрос судебных дел (Арбитраж)
                legal_data = await parser.fetch_legal_cases(inn=inn)
                if legal_data:
                    data["legal_cases"] = legal_data
                await asyncio.sleep(0.3)

                # 4. Запрос долгов и исполнительных производств (ФССП)
                enf_data = await parser.fetch_enforcements(inn=inn)
                if enf_data:
                    data["enforcements"] = enf_data
                await asyncio.sleep(0.3)

                # 5. Запрос госконтрактов (B2G выручка, ФЗ-44, ФЗ-223)
                contract_data = await parser.fetch_contracts(inn=inn)
                if contract_data:
                    data["contracts"] = contract_data
                    
                # Save to ExternalData
                ext_record = ExternalData(
                    startup_id=startup_id,
                    source="checko",
                    source_authority=0.9,
                    data_json=json.dumps(data, ensure_ascii=False)
                )
                session.add(ext_record)
                
                # Also save financials as source="bfo" so backend UI picks it up automatically
                if "financials" in data and isinstance(data["financials"], dict) and data["financials"]:
                    bfo_record = ExternalData(
                        startup_id=startup_id,
                        source="bfo",
                        source_authority=0.9,
                        data_json=json.dumps(data["financials"], ensure_ascii=False)
                    )
                    session.add(bfo_record)
                
                # Check and add new financial records if available
                # Checko parser returns finances inside `bfo_normalized` usually or standard checko response
                # Let's see if we can extract revenue/profit for years < 2020
                if "financials" in data and isinstance(data["financials"], dict):
                    existing_fin_stmt = select(StartupFinancial).where(StartupFinancial.startup_id == startup_id)
                    existing_fins = (await session.execute(existing_fin_stmt)).scalars().all()
                    existing_years = {f.year for f in existing_fins}
                    
                    for year, fin_data in data["financials"].items():
                        try:
                            year = int(year)
                            if year not in existing_years:
                                revenue = fin_data.get("revenue") or 0
                                profit = fin_data.get("net_profit") or 0
                                if revenue > 0 or profit != 0:
                                    new_fin = StartupFinancial(
                                        startup_id=startup_id,
                                        year=year,
                                        revenue=revenue,
                                        profit=profit
                                    )
                                    session.add(new_fin)
                                    existing_years.add(year)
                                    logger.info(f"  Added financial record for year {year}")
                        except ValueError:
                            pass
                            
                await session.commit()
                logger.info(f"  Saved Checko data for INN {inn}")
                
            except Exception as e:
                logger.error(f"  Error fetching Checko data for INN {inn}: {e}")
                await session.rollback()
                
            # Optional: Add small sleep to not overwhelm the API connection
            await asyncio.sleep(0.5)
            
    await parser.close()
    logger.info("Done.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(parse_all())
