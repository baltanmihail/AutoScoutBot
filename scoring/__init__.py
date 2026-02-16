# scoring -- ML pipeline for startup evaluation
#
# Modules:
#   labeler      -- Phase 0: proxy labeling from CSV expert data
#   features     -- Phase 2: 39-dimensional feature engineering
#   train        -- Phase 2: model training (LightGBM / XGBoost, 6 targets)
#   predictor    -- Phase 2: prediction service + SHAP explanations (singleton)
#   ml_scoring   -- Bridge: connects trained models to the Telegram bot

