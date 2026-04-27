import sys

with open("frontend/search.html", "r", encoding="utf-8") as f:
    content = f.read()

# Fix space wrapping
content = content.replace(
    "(списывается 1 запрос выбранной модели).",
    "(списывается 1 запрос выбранной&nbsp;модели)."
)

# Insert History UI
history_ui = """
          <!-- Search History -->
          <div v-if="!hasSearched && searchHistory.length > 0" class="w-full mt-12 transition-all duration-500 animate-fade-in">
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-sm font-semibold text-slate-400 uppercase tracking-wider">История запросов</h3>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div v-for="item in searchHistory" :key="item.id" @click="loadHistory(item.id)" class="glass-panel p-4 rounded-xl border border-white/5 hover:border-blue-500/30 hover:bg-white/5 transition-all cursor-pointer group flex flex-col gap-2 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                <div class="flex items-start justify-between relative z-10">
                  <span class="text-xs text-slate-500">{{ new Date(item.created_at).toLocaleDateString('ru-RU', {day: 'numeric', month: 'short', hour: '2-digit', minute:'2-digit'}) }}</span>
                  <span class="inline-flex items-center px-2 py-0.5 rounded text-[9px] font-medium border uppercase tracking-wider" 
                        :class="item.model_type === 'max' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : (item.model_type === 'pro' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' : 'bg-slate-800 text-slate-300 border-slate-700')">
                    {{ item.model_type }}
                  </span>
                </div>
                <p class="text-sm font-medium text-white line-clamp-2 leading-relaxed relative z-10 group-hover:text-blue-100 transition-colors">
                  {{ item.query_text }}
                </p>
                <div class="flex items-center justify-between mt-auto pt-2 relative z-10">
                  <span class="text-xs text-slate-400">{{ item.results_count }} стартапов найдено</span>
                  <svg class="w-4 h-4 text-slate-500 group-hover:text-blue-400 transition-colors transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
                </div>
              </div>
            </div>
          </div>
"""

# Insert right after model selector
end_model_selector = content.find("<!-- Results Area -->")
if end_model_selector != -1:
    content = content[:end_model_selector] + history_ui + content[end_model_selector:]


# Update Vue setup to include history logic
setup_additions = """
        const searchHistory = ref([]);

        const fetchSearchHistory = async (token) => {
          try {
            const res = await fetch('/api/search/history', {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
              const data = await res.json();
              searchHistory.value = data.history || [];
            }
          } catch (e) {
            console.error("Error fetching history", e);
          }
        };

        const loadHistory = async (queryId) => {
          isSearching.value = true;
          hasSearched.value = true;
          errorMessage.value = '';
          searchResults.value = [];
          searchQuery.value = 'Загрузка запроса...';
          
          try {
            const token = localStorage.getItem('auth_token');
            const res = await fetch(`/api/search/history/${queryId}`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            
            const data = await res.json();
            if (!res.ok) {
              throw new Error(data.detail || 'Ошибка загрузки истории');
            }
            
            searchResults.value = data.results || [];
            
            // Find the query text from history to restore the search box
            const historyItem = searchHistory.value.find(h => h.id === queryId);
            if (historyItem) {
              searchQuery.value = historyItem.query_text;
              modelType.value = historyItem.model_type;
            } else {
              searchQuery.value = 'Исторический запрос';
            }
            
            setTimeout(resizeTextarea, 50);
            
          } catch (e) {
            errorMessage.value = e.message;
          } finally {
            isSearching.value = false;
          }
        };
"""

# Inject setup additions
fetch_profile_limits_idx = content.find("const fetchProfileLimits")
if fetch_profile_limits_idx != -1:
    content = content[:fetch_profile_limits_idx] + setup_additions + content[fetch_profile_limits_idx:]

# Call fetchSearchHistory in onMounted
on_mounted_idx = content.find("fetchProfileLimits(token);", content.find("onMounted("))
if on_mounted_idx != -1:
    insert_str = "fetchProfileLimits(token);\n          fetchSearchHistory(token);"
    content = content[:on_mounted_idx] + insert_str + content[on_mounted_idx + len("fetchProfileLimits(token);"):]

# Update return object
return_idx = content.find("logout,")
if return_idx != -1:
    content = content[:return_idx] + "searchHistory,\n          fetchSearchHistory,\n          loadHistory,\n          " + content[return_idx:]

with open("frontend/search.html", "w", encoding="utf-8") as f:
    f.write(content)
