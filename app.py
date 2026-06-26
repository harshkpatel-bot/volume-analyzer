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
from urllib.parse import urlparse, urljoin
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

# --- 2. Memory & Global Config ---
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

# --- 3. Engine 1: Sitemap Parser Component ---
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
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=12)
        if resp.status_code != 200:
            return []
        content = resp.content
        if url.endswith('.gz') or resp.headers.get('Content-Encoding') == 'gzip':
            try: content = gzip.decompress(content)
            except: pass
        soup = BeautifulSoup(content, 'xml')
        return [loc.text.strip() for loc in soup.find_all('loc') if not loc.text.strip().endswith('.xml')]
    except:
        return []

def extract_sitemap_layer(base_url, headers, proxies=None):
    sitemap_url = get_sitemap_from_robots(base_url, headers, proxies)
    all_urls = []
    nested_sitemaps = []
    try:
        response = requests.get(sitemap_url, headers=headers, proxies=proxies, timeout=12)
        if response.status_code in [200, 403]:
            if response.status_code == 403:
                return {"error": "403 Forbidden on Sitemap. Cloud IP blocked.", "urls": []}
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                    results = executor.map(lambda url: fetch_single_sitemap(url, headers, proxies), nested_sitemaps[:30])
                    for res in results:
                        all_urls.extend(res)
            return {"error": None, "urls": all_urls}
    except Exception as e:
        return {"error": str(e), "urls": []}
    return {"error": "Sitemap target unreachable", "urls": []}

# --- 4. Engine 2: Live HTML Navigation & Link Crawler ---
def extract_live_html_links(base_url, headers, proxies=None):
    """Visits the live homepage and extracts active structural navigation URLs."""
    discovered_urls = []
    try:
        response = requests.get(base_url, headers=headers, proxies=proxies, timeout=12)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                # Resolve relative URLs to complete absolute web links
                absolute_url = urljoin(base_url, href)
                # Keep tracking bounded strictly within the target platform domain
                if urlparse(absolute_url).netloc == urlparse(base_url).netloc:
                    discovered_urls.append(absolute_url)
    except:
        pass
    return list(set(discovered_urls))

# --- 5. Unified Master Processing Pipeline ---
@st.cache_data(show_spinner=False, ttl=1800)
def unified_platform_extraction(base_url, region, proxy_url=None):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{region}-US,en;q=0.9",
        "Connection": "keep-alive"
    }
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    
    # 1. Gather via Sitemap Tree
    sitemap_res = extract_sitemap_layer(base_url, headers, proxies)
    urls_from_sitemap = sitemap_res["urls"]
    
    # 2. Gather via Live Page Visit Discovery
    urls_from_html = extract_live_html_links(base_url, headers, proxies)
    
    # Combined master payload
    combined_urls = list(set(urls_from_sitemap + urls_from_html))
    error_msg = sitemap_res["error"] if (not combined_urls and sitemap_res["error"]) else None
    
    return {"error": error_msg, "urls": combined_urls, "from_sitemap": len(urls_from_sitemap), "from_html": len(urls_from_html)}

@st.cache_data(show_spinner=False)
def process_taxonomy_mapping(urls, keyword, _current_memory):
    categories_data = []
    products_data = []
    
    cat_keywords = ['/category/', '/collections/', '/c/', '/shop/', '/store/', '/women', '/men', '/kids', '/brands/', '/clothing', '/shoes']
    prod_keywords = ['/product/', '/p/', '/item/', '/buy/', '/dp/']
    
    for u in urls:
        u_lower = u.lower()
        # Heuristic rules separating product nodes from category index views
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
                "Category Name": u.split('/')[-1].split('?')[0].replace('-', ' ').title() or "Main Directory",
                "Source URL": u
            })
            
    return pd.DataFrame(categories_data).drop_duplicates(), pd.DataFrame(products_data)

# --- 6. Interface Configuration ---
with st.sidebar:
    st.title("Framework Settings")
    target_url = st.text_input("🔗 Source Platform URL", "https://www.myntra.com")
    region = st.text_input("🌍 Region Code", "IN")
    search_keyword = st.text_input("🔍 Tracking Keyword", "")
    
    st.subheader("🛡️ Network Routing")
    proxy_input = st.text_input(
        "Rotating Proxy Gateway URL", 
        placeholder="http://user:pass@proxy.server.com:port",
        help="Paste residential proxy credentials to avoid cloud infrastructure blocks on protected networks."
    )
    analyze_btn = st.button("🚀 Run Dual-Engine Analysis")

# --- 7. Execution Logic ---
st.title("⚡ Enterprise Volume Analyzer & Hierarchy Mapper")

proxy_to_use = proxy_input.strip() if proxy_input.strip() else None

if analyze_btn:
    with st.spinner(f"Running synchronized sitemap & HTML crawler operations for {target_url}..."):
        result = unified_platform_extraction(target_url, region, proxy_to_use)
        
        if result["error"] and not result["urls"]:
            st.error(f"Execution Aborted: {result['error']}")
        elif not result["urls"]:
            st.warning("Framework accessed target successfully, but network barriers returned empty datasets.")
        else:
            df_categories, df_products = process_taxonomy_mapping(result["urls"], search_keyword, memory)
            st.session_state['total_urls'] = len(result["urls"])
            st.session_state['sitemap_count'] = result["from_sitemap"]
            st.session_state['html_count'] = result["from_html"]
            st.session_state['cat_data'] = df_categories
            st.session_state['product_data'] = df_products
            st.success("Synchronized Extraction Completed!")

# --- 8. The Interactive Dashboard Application ---
if 'product_data' in st.session_state:
    df_cats = st.session_state['cat_data']
    df_products = st.session_state['product_data']
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Extracted Platform URLs", st.session_state['total_urls'])
    col2.metric("Mapped Categories & Nodes", len(df_cats))
    col3.metric("Quantified Product Pages", len(df_products))
    
    st.info(f"💡 Discovery Sources Breakdown: **{st.session_state['sitemap_count']}** entries parsed from XML Sitemaps | **{st.session_state['html_count']}** entries gathered from Live Page Visit Engine.")
    st.divider()
    
    tab1, tab2, tab3 = st.tabs(["📊 Volume & Visual Distribution", "🧠 AI Taxonomy Tuning", "📥 Export Hub"])
    
    with tab1:
        if not df_products.empty:
            vol_df = df_products.groupby(["L1 Category"]).size().reset_index(name="Volume")
            fig = px.pie(vol_df, values='Volume', names='L1 Category', hole=0.4, title="Volume Share by Category Mapping")
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Discovered Product Datatable Preview")
            st.dataframe(df_products.head(500), use_container_width=True) 
        else:
            st.info("Product structures are currently consolidating. Verify keyword configurations if volume matches 0.")
            
        st.subheader("Discovered Categories & Directory Nodes")
        st.dataframe(df_cats.head(500), use_container_width=True)

    with tab2:
        if not df_products.empty:
            correction_product = st.selectbox("Target URL Pattern Reference", df_products["Product Name"].unique())
            new_l1 = st.text_input("Assign Reworked L1 Category")
            if st.button("Commit Overrides to Memory"):
                if correction_product not in memory["category_mappings"]:
                    memory["category_mappings"][correction_product] = {}
                if new_l1: memory["category_mappings"][correction_product]["L1"] = new_l1
                save_memory(memory)
                unified_platform_extraction.clear()
                process_taxonomy_mapping.clear()
                st.success("TAXONOMY RULES UPDATED! Please re-run analysis to generate updated distribution structures.")

    with tab3:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        csv_data = df_products.to_csv(index=False).encode('utf-8')
        st.download_button("📄 Download Core Data Export (CSV)", data=csv_data, file_name=f"platform_taxonomy_export_{timestamp}.csv", mime="text/csv")
