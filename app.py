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

# --- 1. UI/UX Setup & Custom CSS (From Provided HTML) ---
st.set_page_config(page_title="UAE Grocery Volume Analyzer", page_icon="🛒", layout="wide", initial_sidebar_state="expanded")

custom_css = """
<style>
  :root {
      --color-background-primary: #ffffff;
      --color-background-secondary: #f8f9fa;
      --color-border-tertiary: #e5e7eb;
      --color-border-secondary: #d1d5db;
      --color-border-info: #3b82f6;
      --color-text-primary: #111827;
      --color-text-secondary: #4b5563;
      --border-radius-md: 8px;
      --border-radius-lg: 12px;
  }
  
  /* Streamlit Native Overrides */
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] { padding-top: 10px; padding-bottom: 10px; }
  .stButton>button { width: 100%; border-radius: 8px; transition: all 0.3s ease; font-weight: 500; }
  .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
  
  /* Custom HTML UI Integration */
  .section-title { font-size:14px;font-weight:600;color:var(--color-text-secondary);text-transform:uppercase;letter-spacing:.06em;margin:20px 0 16px; }
  .platform-grid { display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:28px; }
  .platform-card { background:var(--color-background-primary);border:1px solid var(--color-border-tertiary);border-radius:var(--border-radius-lg);padding:16px; box-shadow: 0 2px 5px rgba(0,0,0,0.02); }
  .platform-card.featured { border-width:2px;border-color:var(--color-border-info); }
  .plat-header { display:flex;align-items:center;gap:12px;margin-bottom:12px; }
  .plat-icon { width:38px;height:38px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:600;flex-shrink:0; }
  .icon-noon { background:#faeeda;color:#854f0b; }
  .icon-amazon { background:#e6f1fb;color:#0c447c; }
  .icon-insta { background:#fbeaf0;color:#993556; }
  .icon-talabat { background:#faece7;color:#993c1d; }
  .icon-careem { background:#eaf3de;color:#3b6d11; }
  .plat-name { font-size:15px;font-weight:600;color:var(--color-text-primary); }
  .plat-type { font-size:12px;color:var(--color-text-secondary);margin-top:2px; }
  .badge-row { display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 6px; }
  .badge { font-size:11px;padding:3px 10px;border-radius:12px;background:var(--color-background-secondary);color:var(--color-text-secondary);border:1px solid var(--color-border-tertiary); font-weight: 500;}
  .badge.green { background:#eaf3de;color:#3b6d11;border-color:#c4e0a4;}
  .badge.amber { background:#faeeda;color:#854f0b;border-color:#ebd3af;}
  .badge.blue { background:#e6f1fb;color:#0c447c;border-color:#b9d8f6;}
  .badge.red { background:#fcebeb;color:#a32d2d;border-color:#f6caca;}
  .badge.purple { background:#eeedfe;color:#534ab7;border-color:#d4d0fc;}
  .note-row { font-size:12px;color:var(--color-text-secondary);margin-top:10px;padding-top:10px;border-top:1px solid var(--color-border-tertiary); line-height: 1.4; }

  /* Tables */
  .attr-table { width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05);}
  .attr-table th { font-size:12px;font-weight:600;color:var(--color-text-secondary);text-align:left;padding:10px 12px;border-bottom:1px solid var(--color-border-secondary);background:var(--color-background-secondary); }
  .attr-table td { padding:10px 12px;border-bottom:1px solid var(--color-border-tertiary);color:var(--color-text-primary);vertical-align:top; }
  .attr-table tr:hover td { background:#f9fafb; }
  .tick { color:#3b6d11;font-size:15px; font-weight:bold;}
  .cross { color:#a32d2d;font-size:15px; font-weight:bold;}
  .partial { color:#854f0b;font-size:15px; font-weight:bold;}
  .col-plat { text-align:center; }

  /* Volume Metrics */
  .vol-grid { display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:28px; }
  .vol-card { background:white;border: 1px solid var(--color-border-tertiary); border-radius:var(--border-radius-md);padding:16px 18px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);}
  .vol-label { font-size:12px;color:var(--color-text-secondary);margin-bottom:6px; font-weight: 500; text-transform: uppercase;}
  .vol-value { font-size:24px;font-weight:700;color:var(--color-text-primary); }
  .vol-sub { font-size:12px;color:var(--color-border-info);margin-top:4px; font-weight:500;}

  /* Insights */
  .insight-list { list-style:none;padding:0;margin:0 0 24px;display:flex;flex-direction:column;gap:10px; }
  .insight-list li { background:white;border:1px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:14px 18px;font-size:14px;color:var(--color-text-primary);display:flex;gap:12px;align-items:flex-start; line-height:1.5;}
  .insight-list li b { color: var(--color-border-info); }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- 2. Memory & Crawler Setup ---
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

# --- 3. Live Crawler Functions ---
def extract_links_from_url(url, base_url, headers, proxies):
    internal_links = set()
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href'].split('#')[0].strip()
                absolute_url = urljoin(base_url, href)
                if urlparse(absolute_url).netloc == urlparse(base_url).netloc:
                    internal_links.add(absolute_url)
    except:
        pass
    return internal_links

@st.cache_data(show_spinner=False, ttl=1800)
def run_live_site_crawl(base_url, region, max_pages=150, proxy_url=None):
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": f"{region}-US,en;q=0.9"}
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    
    visited_urls = set()
    url_queue = {base_url}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while url_queue and len(visited_urls) < max_pages:
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
                    url_queue.update(future.result().difference(visited_urls))
        time.sleep(0.5)
        
    progress_bar.empty()
    status_text.empty()
    return list(visited_urls)

@st.cache_data(show_spinner=False)
def parse_and_categorize_live_urls(urls, keyword, _current_memory):
    categories_data, products_data = [], []
    cat_keywords = ['/category/', '/collections/', '/c/', '/shop/', '/store/']
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
                "Product URL": u, "Product Name": product_name,
                "Brand": "Extracted Brand", "Pack Size": "Extracted Size", "Price": "Extracted Price",
                "L1 Category": learned_mapping.get("L1", fallback_l1),
                "L2 Category": learned_mapping.get("L2", "N/A"),
            })
        elif any(kw in u_lower for kw in cat_keywords) or u_lower.count('/') <= 4:
            categories_data.append({
                "Category Name": u.split('/')[-1].split('?')[0].replace('-', ' ').title() or "Directory",
                "Source URL": u
            })
            
    return pd.DataFrame(categories_data).drop_duplicates(), pd.DataFrame(products_data)

# --- 4. Sidebar Interface ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3082/3082011.png", width=60) # Grocery Icon
    st.title("Framework Settings")
    target_url = st.text_input("🔗 Target Platform URL", "https://www.instashop.com")
    region = st.text_input("🌍 Region Code", "AE")
    search_keyword = st.text_input("🔍 Tracking Keyword", "Grocery")
    max_crawl_pages = st.number_input("Max Pages to Visit", min_value=10, max_value=2000, value=150, step=50)
    
    st.subheader("🛡️ Network Routing")
    proxy_input = st.text_input("Rotating Proxy URL", placeholder="http://user:pass@proxy.com:port")
    analyze_btn = st.button("🚀 Run Live Extraction")

# --- 5. Main Execution & Layout ---
st.title("🛒 UAE Grocery Platform Analyzer & Live Crawler")

if analyze_btn:
    proxy_to_use = proxy_input.strip() if proxy_input.strip() else None
    st.toast("Initializing live link discovery...", icon="🕷️")
    discovered_urls = run_live_site_crawl(target_url, region, max_crawl_pages, proxy_to_use)
    
    if discovered_urls:
        df_categories, df_products = parse_and_categorize_live_urls(discovered_urls, search_keyword, memory)
        st.session_state['crawled'] = True
        st.session_state['total_urls'] = len(discovered_urls)
        st.session_state['cat_data'] = df_categories
        st.session_state['product_data'] = df_products
        st.success(f"Crawling finished! Successfully visited and parsed {len(discovered_urls)} links.")
    else:
        st.error("Crawler was unable to scrape any URLs.")

# --- 6. The UI Tabs (Mapped exactly to provided HTML) ---
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Attributes", "Volume & Scale", "Insights & Data"])

with tab1:
    # Inject HTML Platform Profiles
    platform_html = """
    <p class="section-title">Platform profiles — Dubai grocery</p>
    <div class="platform-grid">
      <div class="platform-card">
        <div class="plat-header">
          <div class="plat-icon icon-noon">N</div>
          <div><div class="plat-name">Noon Grocery</div><div class="plat-type">Marketplace + quick commerce</div></div>
        </div>
        <div class="badge-row">
          <span class="badge green">Noon Daily</span><span class="badge amber">Noon Minutes</span><span class="badge blue">Noon Express</span>
        </div>
        <div class="badge-row">
          <span class="badge">Delivery: 30 min – 2 hr</span><span class="badge">Min order: AED 0</span>
        </div>
        <div class="note-row">3P marketplace + 1P dark store. Largest SKU depth. Halal flags + EAN trackable.</div>
      </div>
      <div class="platform-card">
        <div class="plat-header">
          <div class="plat-icon icon-amazon">A</div>
          <div><div class="plat-name">Amazon.ae Fresh</div><div class="plat-type">Prime-gated delivery</div></div>
        </div>
        <div class="badge-row">
          <span class="badge blue">Amazon Fresh</span><span class="badge purple">LuLu partnership</span>
        </div>
        <div class="badge-row">
          <span class="badge">Delivery: 2 hr scheduled</span><span class="badge">Min order: AED 50</span>
        </div>
        <div class="note-row">Prime-only access. Partnered stores (LuLu). Rich PLP attributes incl. star rating.</div>
      </div>
      <div class="platform-card featured">
        <div class="plat-header">
          <div class="plat-icon icon-insta">I</div>
          <div><div class="plat-name">Instashop</div><div class="plat-type">On-demand multi-retailer</div></div>
        </div>
        <div class="badge-row">
          <span class="badge green">Now under Talabat</span><span class="badge amber">10,000+ stores</span>
        </div>
        <div class="badge-row">
          <span class="badge">Delivery: ~60 min</span><span class="badge">Acquired: Mar 2026</span>
        </div>
        <div class="note-row">Connects to neighbourhood stores. Deepest sub-brand data. GMV ~$631M.</div>
      </div>
      <div class="platform-card">
        <div class="plat-header">
          <div class="plat-icon icon-talabat">T</div>
          <div><div class="plat-name">Talabat Mart</div><div class="plat-type">Dark-store quick commerce</div></div>
        </div>
        <div class="badge-row">
          <span class="badge red">Talabat Mart</span><span class="badge amber">Grocery + pharma</span>
        </div>
        <div class="badge-row">
          <span class="badge">Delivery: &lt;20 min</span><span class="badge">IPO: Dec 2024</span>
        </div>
        <div class="note-row">Own dark stores. Fastest delivery promise. Instashop merged under Talabat umbrella.</div>
      </div>
      <div class="platform-card">
        <div class="plat-header">
          <div class="plat-icon icon-careem">C</div>
          <div><div class="plat-name">Careem Groceries</div><div class="plat-type">Super-app grocery arm</div></div>
        </div>
        <div class="badge-row">
          <span class="badge green">Careem Quik</span><span class="badge">e& majority owned</span>
        </div>
        <div class="badge-row">
          <span class="badge">Delivery: 30–60 min</span><span class="badge">Range +66% in 2024</span>
        </div>
        <div class="note-row">Super-app model. Limited standalone PLP. Lighter attribute set.</div>
      </div>
    </div>
    """
    st.markdown(platform_html, unsafe_allow_html=True)

with tab2:
    st.markdown('<p class="section-title">Data attributes available on PLP — grocery</p>', unsafe_allow_html=True)
    
    # Inject HTML Attribute Table
    attr_html = """
    <div style="overflow-x:auto;">
    <table class="attr-table">
      <thead>
        <tr>
          <th style="width:25%">Attribute</th>
          <th class="col-plat">Noon</th><th class="col-plat">Amazon</th>
          <th class="col-plat">Instashop</th><th class="col-plat">Talabat</th><th class="col-plat">Careem</th>
        </tr>
      </thead>
      <tbody>
        <tr><td><strong>Product name / title</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td></tr>
        <tr><td><strong>Brand</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="partial">~</span></td></tr>
        <tr><td><strong>Category / subcategory</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td></tr>
        <tr><td><strong>Pack size / volume</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="partial">~</span></td><td class="col-plat"><span class="partial">~</span></td></tr>
        <tr><td><strong>Price & Sale Price (AED)</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td></tr>
        <tr><td><strong>Unit price (per kg/L)</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="partial">~</span></td><td class="col-plat"><span class="cross">✗</span></td><td class="col-plat"><span class="cross">✗</span></td></tr>
        <tr><td><strong>EAN / barcode</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="partial">~</span></td><td class="col-plat"><span class="cross">✗</span></td><td class="col-plat"><span class="cross">✗</span></td></tr>
        <tr><td><strong>Halal certified flag</strong></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="partial">~</span></td><td class="col-plat"><span class="tick">✓</span></td><td class="col-plat"><span class="partial">~</span></td><td class="col-plat"><span class="cross">✗</span></td></tr>
      </tbody>
    </table>
    </div>
    <div style="font-size:13px;color:gray;margin-bottom:20px;">
      <span class="tick">✓</span> Available &nbsp;&nbsp;&nbsp; <span class="partial">~</span> Partial &nbsp;&nbsp;&nbsp; <span class="cross">✗</span> Not available
    </div>
    """
    st.markdown(attr_html, unsafe_allow_html=True)
    
    if st.session_state.get('crawled'):
        st.markdown('<p class="section-title">Live Scraped Attributes Data Table</p>', unsafe_allow_html=True)
        st.dataframe(st.session_state['product_data'], use_container_width=True)

with tab3:
    # Blend static volume insights with live dynamic metrics using the custom HTML grid
    if st.session_state.get('crawled'):
        live_vol_html = f"""
        <p class="section-title">Live Scrape Scale Indicators (Dynamic)</p>
        <div class="vol-grid">
          <div class="vol-card"><div class="vol-label">Crawled Target</div><div class="vol-value">{urlparse(target_url).netloc}</div><div class="vol-sub">Current domain</div></div>
          <div class="vol-card"><div class="vol-label">Links Extracted</div><div class="vol-value">{st.session_state['total_urls']}</div><div class="vol-sub">Total pages visited</div></div>
          <div class="vol-card"><div class="vol-label">Categories Mapped</div><div class="vol-value">{len(st.session_state['cat_data'])}</div><div class="vol-sub">Unique directories</div></div>
          <div class="vol-card"><div class="vol-label">Products Identified</div><div class="vol-value">{len(st.session_state['product_data'])}</div><div class="vol-sub">Items isolated</div></div>
        </div>
        """
        st.markdown(live_vol_html, unsafe_allow_html=True)

    static_vol_html = """
    <p class="section-title">Market Scale Indicators (UAE Platform Baseline)</p>
    <div class="vol-grid">
      <div class="vol-card"><div class="vol-label">Instashop GMV (2025)</div><div class="vol-value">$631M</div><div class="vol-sub">+16% YoY</div></div>
      <div class="vol-card"><div class="vol-label">Talabat + Instashop GMV</div><div class="vol-value">$2.5B+</div><div class="vol-sub">Post-merger</div></div>
      <div class="vol-card"><div class="vol-label">Instashop partner stores</div><div class="vol-value">10,000+</div><div class="vol-sub">UAE + Egypt</div></div>
      <div class="vol-card"><div class="vol-label">Talabat Mart peak delivery</div><div class="vol-value">&lt;20 min</div><div class="vol-sub">Dark store model</div></div>
    </div>
    
    <p class="section-title">Estimated SKU depth — Dubai grocery</p>
    <table class="attr-table">
      <thead><tr><th>Platform</th><th>Est. grocery SKUs</th><th>Categories covered</th></tr></thead>
      <tbody>
        <tr><td>Noon Grocery / Minutes</td><td>50,000 – 80,000+</td><td>Ambient, chilled, frozen, fresh</td></tr>
        <tr><td>Amazon.ae Fresh</td><td>20,000 – 40,000</td><td>Full grocery + specialty</td></tr>
        <tr><td>Instashop (now Talabat)</td><td>100,000+ across stores</td><td>Full grocery, pharma, pets</td></tr>
        <tr><td>Talabat Mart</td><td>5,000 – 15,000</td><td>Grocery essentials, snacks</td></tr>
        <tr><td>Careem Groceries</td><td>5,000 – 10,000</td><td>Essentials, household</td></tr>
      </tbody>
    </table>
    """
    st.markdown(static_vol_html, unsafe_allow_html=True)

with tab4:
    insights_html = """
    <p class="section-title">Key findings & recommendations</p>
    <ul class="insight-list">
      <li><div><b>Merger:</b> Instashop is now part of Talabat — acquired in March 2026. Monitor both endpoints; coverage may overlap significantly.</div></li>
      <li><div><b>Data Integrity:</b> Noon and Amazon offer the richest attribute sets for grocery — including EAN codes, unit pricing, and halal flags.</div></li>
      <li><div><b>Extraction Flags:</b> Pack size data is inconsistent on Talabat Mart and Careem — embedded within the product name string requiring regex logic.</div></li>
      <li><div><b>Geography:</b> Pricing and availability vary by Dubai area. Quick-commerce apps use hyperlocal dark stores, so coverage differs by zone.</div></li>
    </ul>
    """
    st.markdown(insights_html, unsafe_allow_html=True)
    
    st.divider()
    st.markdown('<p class="section-title">Taxonomy & Data Export Hub</p>', unsafe_allow_html=True)
    
    if st.session_state.get('crawled') and not st.session_state['product_data'].empty:
        df_prods = st.session_state['product_data']
        
        c1, c2 = st.columns(2)
        with c1:
            correction_product = st.selectbox("Teach AI: Correct Category Mapping", df_prods["Product Name"].unique())
            new_l1 = st.text_input("Assign Reworked L1 Category")
            if st.button("Commit Overrides to Memory"):
                if correction_product not in memory["category_mappings"]:
                    memory["category_mappings"][correction_product] = {}
                if new_l1: memory["category_mappings"][correction_product]["L1"] = new_l1
                save_memory(memory)
                run_live_site_crawl.clear()
                st.success("Memory Updated! Run crawl again to apply.")
                
        with c2:
            st.write("Download Currently Scraped Artifacts")
            csv_data = df_prods.to_csv(index=False).encode('utf-8')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            st.download_button("📄 Export Live Data (CSV)", data=csv_data, file_name=f"grocery_scrape_{timestamp}.csv", mime="text/csv")
    else:
        st.info("Run the Live Extraction Engine on the sidebar to unlock Data Exports & AI Mapping corrections.")
