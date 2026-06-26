import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import io
import time
import random
import gzip
import concurrent.futures
from urllib.parse import urlparse
from datetime import datetime
import plotly.express as px

# --- 1. UI/UX Setup & Custom CSS ---
st.set_page_config(page_title="Volume Analyzer Pro", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; transition: all 0.3s ease; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
    </style>
""", unsafe_allow_html=True)

# --- 2. Memory & Settings ---
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

# --- 3. Enterprise Sitemap Extraction Engine ---

def get_sitemap_from_robots(base_url, headers, proxies=None):
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        resp = requests.get(robots_url, headers=headers, proxies=proxies, timeout=10)
        if resp.status_code == 200:
            for line in resp.text.split('\n'):
                if line.lower().startswith('sitemap:'):
                    return line.split(':', 1)[1].strip()
    except:
        pass
    return f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"

def fetch_single_sitemap(url, headers, proxies=None):
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        if resp.status_code != 200:
            return []
            
        content = resp.content
        if url.endswith('.gz') or resp.headers.get('Content-Encoding') == 'gzip':
            try:
                content = gzip.decompress(content)
            except:
                pass
                
        soup = BeautifulSoup(content, 'xml')
        return [loc.text.strip() for loc in soup.find_all('loc') if not loc.text.strip().endswith('.xml')]
    except:
        return []

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_sitemap_urls(base_url, region, proxy_url=None):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": f"{region}-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    # Configure proxy dict if provided
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    
    sitemap_url = get_sitemap_from_robots(base_url, headers, proxies)
    
    all_urls = []
    nested_sitemaps = []
    
    try:
        response = requests.get(sitemap_url, headers=headers, proxies=proxies, timeout=15)
        
        if response.status_code == 403:
            return {"error": "403 Forbidden: The platform firewall blocked this cloud IP address. Please provide a valid Rotating Proxy URL in the configuration panel to bypass this.", "urls": []}
        elif response.status_code != 200:
            return {"error": f"Sitemap missing or blocked (HTTP {response.status_code})", "urls": []}
            
        content = response.content
        if sitemap_url.endswith('.gz') or response.headers.get('Content-Encoding') == 'gzip':
            content = gzip.decompress(content)
            
        soup = BeautifulSoup(content, 'xml')
        
        for loc in soup.find_all('loc'):
            url_text = loc.text.strip()
            if url_text.endswith('.xml') or url_text.endswith('.xml.gz'):
                nested_sitemaps.append(url_text)
            else:
                all_urls.append(url_text)
                
        if nested_sitemaps:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = executor.map(lambda url: fetch_single_sitemap(url, headers, proxies), nested_sitemaps[:50])
                for res in results:
                    all_urls.extend(res)
                    
        return {"error": None, "urls": list(set(all_urls))}
    except Exception as e:
        return {"error": str(e), "urls": []}

@st.cache_data(show_spinner=False)
def categorize_and_map_volume(urls, keyword, _current_memory):
    categories_data = []
    products_data = []
    cat_keywords = ['/category/', '/collections/', '/c/', '/shop/', '/store/', '/women', '/men', '/kids', '/brands/']
    prod_keywords = ['/product/', '/p/', '/item/', '/buy/', '/dp/']
    
    for u in urls:
        u_lower = u.lower()
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
                "Category Name": u.split('/')[-1].replace('-', ' ').title() or "Root",
                "Source URL": u
            })
            
    return pd.DataFrame(categories_data).drop_duplicates(), pd.DataFrame(products_data)

# --- 4. Sidebar ---
with st.sidebar:
    st.title("Framework Config")
    target_url = st.text_input("🔗 Source Platform URL", "https://www.myntra.com")
    region = st.text_input("🌍 Region Code", "IN")
    search_keyword = st.text_input("🔍 Tracking Keyword", "")
    
    st.subheader("🛡️ Network Routing (Optional)")
    proxy_input = st.text_input(
        "Rotating Proxy URL", 
        placeholder="http://username:password@proxy.server.com:port",
        help="Paste your rotating residential proxy link here to avoid 403 blocks on enterprise networks."
    )
    
    analyze_btn = st.button("🚀 Run Volume Analysis")

# --- 5. Main Execution ---
st.title("⚡ Enterprise Sitemap Mapper")

# Handle empty string inputs for proxies safely
proxy_to_use = proxy_input.strip() if proxy_input.strip() else None

if analyze_btn:
    with st.spinner(f"Running routed extraction for {target_url}..."):
        sitemap_result = fetch_sitemap_urls(target_url, region, proxy_to_use)
        
        if sitemap_result["error"]:
            st.error(sitemap_result["error"])
        elif not sitemap_result["urls"]:
            st.warning("Sitemap connected, but returned zero crawlable paths.")
        else:
            df_categories, df_products = categorize_and_map_volume(sitemap_result["urls"], search_keyword, memory)
            st.session_state['total_urls'] = len(sitemap_result["urls"])
            st.session_state['cat_data'] = df_categories
            st.session_state['product_data'] = df_products
            st.success("Extraction Complete!")

# --- 6. Dashboard App ---
if 'product_data' in st.session_state:
    df_cats = st.session_state['cat_data']
    df_products = st.session_state['product_data']
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Platform URLs", st.session_state['total_urls'])
    col2.metric("Categories Found", len(df_cats))
    col3.metric("Products Found", len(df_products))
    
    tab1, tab2, tab3 = st.tabs(["📊 Volume & Visuals", "🧠 AI Corrections", "📥 Export Data"])
    
    with tab1:
        if not df_products.empty:
            vol_df = df_products.groupby(["L1 Category"]).size().reset_index(name="Volume")
            fig = px.pie(vol_df, values='Volume', names='L1 Category', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_products.head(500), use_container_width=True) 
        else:
            st.info("No specific product structures found.")

    with tab2:
        if not df_products.empty:
            correction_product = st.selectbox("Select Target URL Pattern", df_products["Product Name"].unique())
            new_l1 = st.text_input("Assign New L1 Category")
            if st.button("Update Knowledge Base"):
                if correction_product not in memory["category_mappings"]:
                    memory["category_mappings"][correction_product] = {}
                if new_l1: memory["category_mappings"][correction_product]["L1"] = new_l1
                save_memory(memory)
                fetch_sitemap_urls.clear()
                categorize_and_map_volume.clear()
                st.success("Memory updated! Please re-run analysis to apply.")

    with tab3:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        if not df_products.empty:
            csv_data = df_products.to_csv(index=False).encode('utf-8')
            st.download_button("📄 Download CSV", data=csv_data, file_name=f"sitemap_{timestamp}.csv", mime="text/csv")
