import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import io
import time
import random
import concurrent.futures
from urllib.parse import urlparse, urljoin
from datetime import datetime
import plotly.express as px

# --- 1. UI/UX Setup & Custom CSS ---
st.set_page_config(page_title="Live Volume Analyzer", page_icon="🕷️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; transition: all 0.3s ease; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
    </style>
""", unsafe_allow_html=True)

# --- 2. Memory Management ---
MEMORY_FILE = "framework_memory.json"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
]

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"category_mappings": {}}

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)

memory = load_memory()

# --- 3. Recursive Live Crawler Engine ---

def extract_links_from_url(url, base_url, headers, proxies):
    """Visits a single live URL and extracts all valid internal links."""
    internal_links = set()
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href'].split('#')[0].strip() # Strip anchors
                absolute_url = urljoin(base_url, href)
                
                # Enforce that the link stays within the same website domain
                if urlparse(absolute_url).netloc == urlparse(base_url).netloc:
                    internal_links.add(absolute_url)
    except:
        pass
    return internal_links

@st.cache_data(show_spinner=False, ttl=1800)
def run_live_site_crawl(base_url, region, max_pages=200, proxy_url=None):
    """Recursively visits the platform pages to map out URLs and taxonomy live."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{region}-US,en;q=0.9",
        "Connection": "keep-alive"
    }
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    
    visited_urls = set()
    url_queue = {base_url}
    
    # Progress visualization containers
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Multi-threaded crawler loop
    while url_queue and len(visited_urls) < max_pages:
        # Take a batch of URLs to scan in parallel
        current_batch = list(url_queue)[:10]
        url_queue = url_queue.difference(current_batch)
        
        status_text.text(f"Crawling live nodes... Visited: {len(visited_urls)} / Max: {max_pages}")
        progress_bar.progress(min(len(visited_urls) / max_pages, 1.0))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(extract_links_from_url, url, base_url, headers, proxies): url for url in current_batch}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                if url not in visited_urls:
                    visited_urls.add(url)
                    new_links = future.result()
                    # Add newly discovered links to queue if they haven't been visited
                    url_queue.update(new_links.difference(visited_urls))
                    
        time.sleep(0.5) # Polite delay between batches
        
    progress_bar.empty()
    status_text.empty()
    return list(visited_urls)

@st.cache_data(show_spinner=False)
def parse_and_categorize_live_urls(urls, keyword, _current_memory):
    categories_data = []
    products_data = []
    
    cat_keywords = ['/category/', '/collections/', '/c/', '/shop/', '/store/', '/women', '/men', '/kids', '/brands/']
    prod_keywords = ['/product/', '/p/', '/item/', '/buy/', '/dp/']
    
    for u in urls:
        u_lower = u.lower()
        # Heuristic rules to separate catalog listings from true product item pages
        is_product = any(kw in u_lower for kw in prod_keywords) or (u_lower.count('/') > 3 and any(char.isdigit() for char in u.split('/')[-1]))
        
        if is_product:
            product_name = u.split('/')[-1].split('?')[0].replace('-', ' ').replace('.html', '').title()
            learned_mapping = _current_memory["category_mappings"].get(product_name, {})
            fallback_l1 = "General Products"
            if keyword and keyword.lower() in u_lower: fallback_l1 = keyword.capitalize()
            
            products_data.append({
                "Product URL": u,
                "Product Name": product_name,
                "L1 Category": learned_mapping.get("L1", fallback_l1),
                "L2 Category": learned_mapping.get("L2", "N/A"),
            })
        elif any(kw in u_lower for kw in cat_keywords) or u_lower.count('/') <= 4:
            categories_data.append({
                "Category Name": u.split('/')[-1].split('?')[0].replace('-', ' ').title() or "Home/Directory",
                "Source URL": u
            })
            
    return pd.DataFrame(categories_data).drop_duplicates(), pd.DataFrame(products_data)

# --- 4. Sidebar Interface ---
with st.sidebar:
    st.title("Framework Settings")
    target_url = st.text_input("🔗 Source Platform URL", "https://www.myntra.com")
    region = st.text_input("🌍 Region Code", "IN")
    search_keyword = st.text_input("🔍 Tracking Keyword", "")
    
    st.subheader("⚙️ Crawler Limits")
    max_crawl_pages = st.number_input("Max Pages to Visit", min_value=10, max_value=2000, value=150, step=50,
                                      help="Higher numbers map more items but take longer to complete.")
    
    st.subheader("🛡️ Network Routing")
    proxy_input = st.text_input(
        "Rotating Proxy Gateway URL", 
        placeholder="http://user:pass@proxy.server.com:port"
    )
    analyze_btn = st.button("🚀 Run Live Website Crawl")

# --- 5. Main Execution Loop ---
st.title("⚡ Live Page Crawler & Taxonomy Mapper")
st.markdown("This framework bypasses sitemaps completely by visiting the target destination live, mapping links sequentially.")

proxy_to_use = proxy_input.strip() if proxy_input.strip() else None

if analyze_btn:
    st.toast("Initializing live link discovery layer...", icon="🕷️")
    discovered_urls = run_live_site_crawl(target_url, region, max_crawl_pages, proxy_to_use)
    
    if not discovered_urls:
        st.error("Crawler was unable to scrape any URLs. Verify your target URL, network proxy settings, or cloud hosting blockages.")
    else:
        df_categories, df_products = parse_and_categorize_live_urls(discovered_urls, search_keyword, memory)
        st.session_state['total_urls'] = len(discovered_urls)
        st.session_state['cat_data'] = df_categories
        st.session_state['product_data'] = df_products
        st.success(f"Crawling finished! Successfully visited and parsed {len(discovered_urls)} platform locations.")

# --- 6. Analytics Dashboard ---
if 'product_data' in st.session_state:
    df_cats = st.session_state['cat_data']
    df_products = st.session_state['product_data']
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Unique Visited URLs", st.session_state['total_urls'])
    col2.metric("Mapped Categories Found", len(df_cats))
    col3.metric("Quantified Product Pages", len(df_products))
    
    st.divider()
    
    tab1, tab2, tab3 = st.tabs(["📊 Volume Analytics", "🧠 AI Taxonomy Tuning", "📥 Export Hub"])
    
    with tab1:
        if not df_products.empty:
            vol_df = df_products.groupby(["L1 Category"]).size().reset_index(name="Volume")
            fig = px.pie(vol_df, values='Volume', names='L1 Category', hole=0.4, title="Volume Share via Live Links")
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Discovered Product Log")
            st.dataframe(df_products, use_container_width=True) 
        else:
            st.info("No specific product structures identified yet inside the current depth pool.")
            
        st.subheader("Discovered Category & Directory Nodes")
        st.dataframe(df_cats, use_container_width=True)

    with tab2:
        if not df_products.empty:
            correction_product = st.selectbox("Target URL Pattern Reference", df_products["Product Name"].unique())
            new_l1 = st.text_input("Assign Reworked L1 Category")
            if st.button("Commit Overrides to Memory"):
                if correction_product not in memory["category_mappings"]:
                    memory["category_mappings"][correction_product] = {}
                if new_l1: memory["category_mappings"][correction_product]["L1"] = new_l1
                save_memory(memory)
                run_live_site_crawl.clear()
                parse_and_categorize_live_urls.clear()
                st.success("Taxonomy mapping rule stored. Re-run analysis to generate updated metric frames.")

    with tab3:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        csv_data = df_products.to_csv(index=False).encode('utf-8')
        st.download_button("📄 Download Live Extraction Export (CSV)", data=csv_data, file_name=f"live_crawl_export_{timestamp}.csv", mime="text/csv")
