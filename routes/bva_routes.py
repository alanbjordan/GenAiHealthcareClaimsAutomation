# routes/bva_routes.py - BVA routes for the VA Decision API.

import math
from datetime import datetime

import requests
import chardet
from bs4 import BeautifulSoup
from flask import Blueprint, request, jsonify, Response

bva_bp = Blueprint('bva_bp', __name__)

def log_with_timing(prev_time, message):
    current_time = datetime.utcnow()
    if prev_time is None:
        elapsed = 0.0
    else:
        elapsed = (current_time - prev_time).total_seconds()
    print(f"[{current_time.isoformat()}] {message} (Elapsed: {elapsed:.4f}s)")
    return current_time

@bva_bp.route('/bva_search', methods=['GET'])
def bva_search():
    t = log_with_timing(None, f"[bva_search] Called with method {request.method}")


    query = request.args.get('query')
    if not query:
        t = log_with_timing(t, "[bva_search][GET] Missing 'query' parameter.")
        return jsonify({"error": "Query parameter is required"}), 400

    page = request.args.get('page', default=1, type=int)
    if page < 1:
        page = 1

    t = log_with_timing(t, f"[bva_search][GET] Received query={query}, page={page}")
    results, total_results, t = fetch_page("https://search.usa.gov/search/docs", query, page, t)

    if total_results is not None:
        total_pages = math.ceil(total_results / 20.0)
    else:
        total_pages = 1 if results else 0

    t = log_with_timing(t, f"[bva_search][GET] Returning {len(results)} results for page={page}, total_results={total_results}, total_pages={total_pages}.")
    return jsonify({"results": results, "totalResults": total_results, "totalPages": total_pages}), 200

def fetch_page(base_url, query, page, timing_prev):
    t = log_with_timing(timing_prev, f"[fetch_page] Fetching page={page} for query='{query}'")

    # VA site returns 20 results per page
    params = {
        "affiliate": "bvadecisions",
        "query": query,
        "page": page
    }

    try:
        response = requests.get(base_url, params=params, timeout=10)
        t = log_with_timing(t, f"[fetch_page] Received status code {response.status_code} for page={page}")
        if response.status_code != 200:
            t = log_with_timing(t, f"[fetch_page][ERROR] Bad status code {response.status_code}. Returning empty results.")
            return [], None, t

        soup = BeautifulSoup(response.text, "html.parser")
        results_div = soup.find("div", id="results")
        if not results_div:
            t = log_with_timing(t, f"[fetch_page] No results found for query='{query}', page={page}.")
            return [], None, t

        # Extract total results
        total_results = None
        results_count_li = soup.find("li", id="results-count")
        if results_count_li:
            span = results_count_li.find("span")
            if span and span.text:
                # e.g. "91,386 results"
                text = span.text.strip()
                digits_only = "".join(ch for ch in text if ch.isdigit())
                if digits_only.isdigit():
                    total_results = int(digits_only)

        page_results = []
        for result in results_div.find_all("div", class_="content-block-item result"):
            title_tag = result.find("h4", class_="title").find("a")
            description_tag = result.find("span", class_="description")
            if title_tag and description_tag:
                page_results.append({
                    "title": title_tag.text.strip(),
                    "url": title_tag["href"].strip(),
                    "description": description_tag.text.strip(),
                })

        t = log_with_timing(t, f"[fetch_page] Returning {len(page_results)} results for page={page}.")
        return page_results, total_results, t

    except requests.exceptions.Timeout:
        t = log_with_timing(t, f"[fetch_page][ERROR] Timeout occurred for query='{query}', page={page}.")
        return [], None, t
    except Exception as e:
        t = log_with_timing(t, f"[fetch_page][ERROR] Exception: {e}")
        return [], None, t

@bva_bp.route('/bva_decision_text', methods=['GET'])
def bva_decision_text():
    t = log_with_timing(None, f"[bva_decision_text] Called with method {request.method}")


    url = request.args.get('url')
    if not url:
        t = log_with_timing(t, "[bva_decision_text][GET][ERROR] Missing 'url' parameter.")
        return jsonify({"error": "Must provide a url parameter"}), 400

    t = log_with_timing(t, f"[bva_decision_text][GET] Fetching decision text from url={url}")
    try:
        dec_response = requests.get(url, timeout=10)
        t = log_with_timing(t, f"[bva_decision_text][GET] Received status code {dec_response.status_code}")
        if dec_response.status_code != 200:
            t = log_with_timing(t, f"[bva_decision_text][GET][ERROR] Unable to retrieve decision text from {url}")
            return jsonify({"error": "Unable to retrieve decision text"}), 404

        dec_response.encoding = dec_response.apparent_encoding or 'utf-8'
        full_text = dec_response.text
        response = jsonify({"fullText": full_text})
        response.headers["Access-Control-Allow-Origin"] = "*"
        t = log_with_timing(t, "[bva_decision_text][GET] Returning decision text.")
        return response, 200

    except requests.exceptions.Timeout:
        t = log_with_timing(t, f"[bva_decision_text][GET][ERROR] Timeout retrieving decision text from {url}")
        return jsonify({"error": "Timeout retrieving decision text"}), 504
    except Exception as e:
        t = log_with_timing(t, f"[bva_decision_text][GET][ERROR] Exception occurred while fetching full decision text from {url}: {e}")
        return jsonify({"error": "Unable to retrieve decision text"}), 500

@bva_bp.route('/bva_support', methods=['GET'])
def bva_support():
    t = log_with_timing(None, f"[bva_support] Called with method {request.method}")

    condition_tag = request.args.get('query')
    if not condition_tag:
        return jsonify({"error": "Missing 'query' parameter"}), 400

    print(f"Condition tag from query: {condition_tag}")

    return jsonify({
        "message": f"Below are the top 5 Board of Veterans’ Appeals (BVA) decisions that closely match the veteran’s condition {condition_tag}."
    }), 200

@bva_bp.route('/bva_decision_text_proxy', methods=['GET'])
def bva_decision_text_proxy():
    t = log_with_timing(None, f"[bva_decision_text_proxy] Called with method {request.method}")


    url = request.args.get('url')
    if not url:
        t = log_with_timing(t, "[bva_decision_text_proxy][GET][ERROR] Missing 'url' parameter.")
        return jsonify({"error": "Must provide a 'url' parameter"}), 400

    t = log_with_timing(t, f"[bva_decision_text_proxy][GET] Fetching raw decision text from url={url}")
    try:
        dec_response = requests.get(url, timeout=10)
        t = log_with_timing(t, f"[bva_decision_text_proxy][GET] Received status code {dec_response.status_code}")
        if dec_response.status_code != 200:
            t = log_with_timing(t, f"[bva_decision_text_proxy][GET][ERROR] Unable to retrieve decision text from {url}")
            return jsonify({"error": "Unable to retrieve decision text"}), 404

        # --- Chardet-based encoding detection ---
        raw_bytes = dec_response.content
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected['encoding'] or 'utf-8'
        
        # Decode into a Python string using the detected (or fallback) encoding
        decoded_text = raw_bytes.decode(detected_encoding, errors='replace')

        # Return decoded text as plain text (UTF-8)
        response = Response(decoded_text, mimetype='text/plain; charset=utf-8')
        response.headers["Access-Control-Allow-Origin"] = "*"
        t = log_with_timing(t, "[bva_decision_text_proxy][GET] Returning decoded decision text.")
        return response, 200

    except requests.exceptions.Timeout:
        t = log_with_timing(t, f"[bva_decision_text_proxy][GET][ERROR] Timeout retrieving decision text from {url}")
        return jsonify({"error": "Timeout retrieving decision text"}), 504
    except Exception as e:
        t = log_with_timing(t, f"[bva_decision_text_proxy][GET][ERROR] Exception occurred: {e}")
        return jsonify({"error": "Unable to retrieve decision text"}), 500
