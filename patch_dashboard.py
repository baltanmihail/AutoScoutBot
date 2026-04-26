import re

with open("frontend/dashboard.html", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the static <tbody> with a dynamic one
tbody_pattern = r'<tbody class="divide-y divide-white/5 bg-transparent">.*?</tbody>'

new_tbody = """<tbody class="divide-y divide-white/5 bg-transparent">
                <tr v-if="topStartups.length === 0" class="hover:bg-white/5 transition-colors group">
                  <td colspan="9" class="px-3 py-8 text-center text-slate-400">
                    <svg class="mx-auto h-8 w-8 text-slate-600 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
                    </svg>
                    Загрузка стартапов...
                  </td>
                </tr>
                <tr v-for="startup in topStartups" :key="startup.id" class="hover:bg-white/5 transition-colors cursor-pointer group">
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex items-center">
                      <div class="flex-shrink-0 h-9 w-9 bg-gradient-to-br from-blue-500/20 to-blue-600/20 border border-blue-500/30 rounded-xl flex items-center justify-center text-blue-400 font-bold shadow-inner group-hover:scale-105 transition-transform">
                        {{ startup.name.charAt(0).toUpperCase() }}
                      </div>
                      <div class="ml-2.5">
                        <div class="text-sm font-semibold text-white truncate max-w-[150px]">{{ startup.name }}</div>
                        <div class="text-[9px] text-slate-500 font-mono mt-0.5">ИНН {{ startup.inn || 'Не указан' }}</div>
                      </div>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <details class="group/desc">
                      <summary class="cursor-pointer list-none flex flex-col items-start gap-1">
                        <div class="flex items-center gap-1.5 hover:bg-slate-800/50 p-1 -ml-1 rounded transition-colors">
                          <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800/80 text-slate-300 border border-slate-700/50 truncate max-w-[120px]">
                            {{ startup.cluster || 'Без кластера' }}
                          </span>
                          <svg class="w-3 h-3 text-slate-500 group-open/desc:rotate-180 transition-transform shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                        </div>
                      </summary>
                      <div class="text-[9px] text-slate-400 max-w-[150px] whitespace-normal mt-1 leading-relaxed bg-dark-900/50 p-2 rounded border border-white/5 shadow-inner line-clamp-4">
                        {{ startup.company_description }}
                      </div>
                    </details>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex flex-col gap-1">
                      <div class="flex items-center">
                        <span class="text-xs font-bold text-emerald-400 w-6">{{ startup.ml_score ? startup.ml_score.toFixed(1) : '-' }}</span>
                        <div v-if="startup.ml_score" class="w-14 bg-dark-900 rounded-full h-1 border border-white/5 ml-1 overflow-hidden">
                          <div class="bg-gradient-to-r from-emerald-500 to-emerald-400 h-1 rounded-full shadow-[0_0_10px_rgba(52,211,153,0.5)]" :style="`width: ${(startup.ml_score/10)*100}%`"></div>
                        </div>
                      </div>
                      <span class="text-[9px] text-slate-500">Скор: {{ startup.score_overall ? startup.score_overall.toFixed(1) : '-' }}</span>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex flex-col gap-1">
                      <span class="text-[9px] text-slate-300"><span class="text-slate-500">Основан:</span> {{ startup.year_founded || '-' }}</span>
                      <span class="text-[9px] text-emerald-400"><span class="text-slate-500">Статус:</span> {{ startup.status || '-' }}</span>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex flex-col gap-0.5">
                      <span class="text-[9px] text-slate-300"><span class="text-slate-500">TRL:</span> MVP</span>
                      <span class="text-[9px] text-slate-300"><span class="text-slate-500">Команда:</span> -</span>
                      <span class="text-[8.5px] text-blue-400 font-semibold"><span class="text-slate-500 font-normal">Тренд:</span> Рост</span>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex flex-col gap-0.5">
                      <span class="text-[9px] font-semibold text-blue-400">-</span>
                      <span class="text-[9px] text-slate-500">Seed</span>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex flex-col gap-0.5">
                      <span class="text-[9px] text-emerald-400 font-bold">IRR ~35%</span>
                      <span class="text-[9px] text-slate-400">ROI 2.5x</span>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap">
                    <div class="flex flex-col gap-0.5 w-14">
                      <span class="text-[10px] font-bold text-emerald-400">Средний</span>
                      <div class="w-full bg-dark-900 rounded-full h-1 border border-white/5 overflow-hidden">
                        <div class="bg-gradient-to-r from-emerald-500 to-emerald-400 h-1 rounded-full" style="width: 50%"></div>
                      </div>
                    </div>
                  </td>
                  <td class="px-3 py-3 whitespace-nowrap text-right">
                    <button class="text-blue-400 hover:text-white transition-colors bg-blue-500/10 hover:bg-blue-500/30 px-2.5 py-1 rounded text-[10px] border border-blue-500/20 font-semibold shadow-sm flex items-center justify-end gap-1 ml-auto">
                      Отчет
                      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                    </button>
                  </td>
                </tr>
              </tbody>"""

new_content = re.sub(tbody_pattern, new_tbody, content, flags=re.DOTALL)

# Add logic to fetch startups
setup_pattern = r'const logout = \(\) => {'
fetch_logic = """const topStartups = ref([]);
        const fetchTopStartups = async () => {
          try {
            const token = localStorage.getItem('auth_token');
            const res = await fetch('/api/score/top', {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
              const data = await res.json();
              topStartups.value = data.top_startups || [];
            }
          } catch (e) {
            console.error("Error fetching top startups", e);
          }
        };

        onMounted(() => {
          fetchTopStartups();
        });

        const logout = () => {"""

new_content = new_content.replace("const logout = () => {", fetch_logic)

# Return topStartups
return_pattern = r'logout,\n          showCalculator,'
return_logic = "logout,\n          topStartups,\n          showCalculator,"
new_content = new_content.replace(return_pattern, return_logic)

with open("frontend/dashboard.html", "w", encoding="utf-8") as f:
    f.write(new_content)
