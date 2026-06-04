"""
AI Briefing RAG Search — Flask web interface for semantic search.

Searches across all indexed briefings (PDF items, raw articles, learning guides)
using Qdrant in-memory vector similarity + optional date/source/difficulty filters.

Usage:
  python search_ui.py [port]
  Opens at http://localhost:18888 (or custom port)

Dependencies: pip install qdrant-client sentence-transformers flask pypdf
"""
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from flask import Flask, request, jsonify, render_template_string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import REPORTS_ROOT, SNAPSHOT_PATH, KNOWLEDGE_ROOT, PROJECT_DIRS_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_model = None
_client = None
_jobs = {}
_jobs_lock = threading.Lock()

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Briefing Search</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f0f2f5; color: #1a1a2e; line-height: 1.6; }
  .container { max-width: 900px; margin: 0 auto; padding: 20px; }
  h1 { color: #1a1a2e; margin-bottom: 4px; font-size: 1.8em; }
  .subtitle { color: #666; margin-bottom: 20px; font-size: 0.95em; }
  .stats { background: #e8f4f8; padding: 8px 16px; border-radius: 6px;
           margin-bottom: 20px; font-size: 0.9em; color: #2c5f7c; }
  .search-box { display: flex; gap: 10px; margin-bottom: 12px; }
  .search-box input { flex: 1; padding: 12px 16px; border: 2px solid #ddd;
                       border-radius: 8px; font-size: 1em; outline: none;
                       transition: border-color 0.2s; }
  .search-box input:focus { border-color: #4a90d9; }
  .search-box button { padding: 12px 28px; background: #4a90d9; color: white;
                        border: none; border-radius: 8px; font-size: 1em;
                        cursor: pointer; transition: background 0.2s; }
  .search-box button:hover { background: #357abd; }
  .filters { display: none; background: white; padding: 16px; border-radius: 8px;
             margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .filters.open { display: block; }
  .filter-toggle { color: #4a90d9; cursor: pointer; font-size: 0.9em;
                   margin-bottom: 8px; display: inline-block; }
  .filter-row { display: flex; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
  .filter-row label { font-size: 0.85em; color: #555; }
  .filter-row input, .filter-row select { padding: 6px 10px; border: 1px solid #ddd;
                                           border-radius: 4px; font-size: 0.9em; }
  .result { background: white; padding: 16px 20px; border-radius: 8px;
            margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            border-left: 4px solid #4a90d9; }
  .result h3 { font-size: 1.05em; margin-bottom: 6px; }
  .result .meta { font-size: 0.82em; color: #666; margin-bottom: 8px; }
  .result .meta .badge { display: inline-block; padding: 1px 8px; border-radius: 10px;
                         font-weight: 600; font-size: 0.8em; margin-right: 6px; }
  .badge-news { background: #e3f2fd; color: #1565c0; }
  .badge-raw { background: #f3e5f5; color: #7b1fa2; }
  .badge-guide { background: #e8f5e9; color: #2e7d32; }
  .confidence-badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
                      font-weight: 600; font-size: 0.75em; margin-left: 8px; vertical-align: middle; }
  .conf-high { background: #e8f5e9; color: #2e7d32; }
  .conf-medium { background: #fff3e0; color: #e65100; }
  .conf-low { background: #fce4ec; color: #c62828; }
  .query-confidence { padding: 6px 14px; border-radius: 6px; font-size: 0.85em;
                      margin-bottom: 10px; display: inline-block; }
  .qconf-high { background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }
  .qconf-medium { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }
  .qconf-low { background: #fce4ec; color: #c62828; border: 1px solid #ef9a9a; }
  .result .preview { font-size: 0.92em; color: #444; white-space: pre-wrap; }
  .result a { color: #4a90d9; text-decoration: none; }
  .result a:hover { text-decoration: underline; }
  .score { float: right; font-size: 0.8em; color: #999; }
  .loading { text-align: center; padding: 40px; color: #999; display: none; }
  .no-results { text-align: center; padding: 40px; color: #999; }
  #results { min-height: 100px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="container">
  <h1>AI Briefing RAG Search</h1>
  <p class="subtitle">Semantic search across daily AI briefings, raw articles, and learning guides</p>
  <div class="stats">{{ stats }}</div>

  <div style="margin-bottom:16px;display:flex;gap:8px">
    <button onclick="showTab('search')" id="tab-search" style="padding:8px 20px;border:2px solid #4a90d9;background:#4a90d9;color:white;border-radius:6px;cursor:pointer;font-size:0.95em">Search</button>
    <button onclick="showTab('library')" id="tab-library" style="padding:8px 20px;border:2px solid #4a90d9;background:white;color:#4a90d9;border-radius:6px;cursor:pointer;font-size:0.95em">Library</button>
    <button onclick="showTab('analysis')" id="tab-analysis" style="padding:8px 20px;border:2px solid #4a90d9;background:white;color:#4a90d9;border-radius:6px;cursor:pointer;font-size:0.95em">Knowledge Explorer</button>
    <button onclick="showTab('eval')" id="tab-eval" style="padding:8px 20px;border:2px solid #4a90d9;background:white;color:#4a90d9;border-radius:6px;cursor:pointer;font-size:0.95em">RAG Eval</button>
  </div>

  <div id="search-tab">
  <div class="search-box">
    <input type="text" id="query" placeholder="e.g. transformer attention, FHIR AI integration, LoRA fine-tuning"
           autofocus>
    <button onclick="doSearch()">Search</button>
  </div>

  <span class="filter-toggle" onclick="toggleFilters()">Filters &#9660;</span>
  <div class="filters" id="filters">
    <div class="filter-row">
      <div><label>From</label><br><input type="date" id="date_from"></div>
      <div><label>To</label><br><input type="date" id="date_to"></div>
      <div><label>Source</label><br><input type="text" id="source" placeholder="e.g. arxiv"></div>
    </div>
    <div class="filter-row">
      <div><label>Difficulty</label><br>
        <select id="difficulty">
          <option value="">All</option>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
        </select>
      </div>
      <div><label>Type</label><br>
        <select id="item_type">
          <option value="">All</option>
          <option value="news_item">News (PDF)</option>
          <option value="raw_content">Raw Articles</option>
          <option value="learning_guide">Learning Guides</option>
          <option value="book_chapter">Books</option>
          <option value="project_doc">Projects</option>
          <option value="personal_note">Notes</option>
          <option value="task">Tasks</option>
          <option value="wiki_page">Wiki Pages</option>
          <option value="code_doc">Code Docs</option>
        </select>
      </div>
      <div><label>Max Results</label><br>
        <input type="number" id="top_k" value="3" min="1" max="30" style="width:60px">
      </div>
      <div><label>Min Score</label><br>
        <input type="number" id="min_score" value="0.5" min="0" max="1" step="0.05" style="width:70px">
      </div>
    </div>
  </div>

  <div class="loading" id="loading">Searching...</div>
  <div id="results"></div>
  </div>

  <div id="library-tab" style="display:none">
    <div style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <select id="lib-type" onchange="loadLibrary()" style="padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:0.95em">
        <option value="">All Types</option>
        <option value="news_item">News (PDF)</option>
        <option value="raw_content">Raw Articles</option>
        <option value="learning_guide">Learning Guides</option>
        <option value="book_chapter">Books</option>
        <option value="project_doc">Projects</option>
        <option value="personal_note">Notes</option>
        <option value="task">Tasks</option>
        <option value="wiki_page">Wiki Pages</option>
        <option value="code_doc">Code Docs</option>
      </select>
      <span id="lib-stats" style="color:#666;font-size:0.9em"></span>
    </div>
    <div id="library-results"></div>
  </div>

  <div id="analysis-tab" style="display:none">
    <div style="margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <button id="btn-index-new" onclick="indexNew()" style="padding:10px 22px;background:#2e7d32;color:white;border:none;border-radius:8px;font-size:0.95em;cursor:pointer;display:flex;align-items:center;gap:6px;transition:background 0.2s">
        <span style="font-size:1.2em">&#8635;</span> Index New Briefings
      </button>
      <button id="btn-refresh-knowledge" onclick="refreshKnowledge()" style="padding:10px 22px;background:#1565c0;color:white;border:none;border-radius:8px;font-size:0.95em;cursor:pointer;display:flex;align-items:center;gap:6px;transition:background 0.2s">
        <span style="font-size:1.2em">&#128218;</span> Refresh Knowledge Docs
      </button>
      <button id="btn-reindex-projects" onclick="reindexProjects()" style="padding:10px 22px;background:#7b1fa2;color:white;border:none;border-radius:8px;font-size:0.95em;cursor:pointer;display:flex;align-items:center;gap:6px;transition:background 0.2s">
        <span style="font-size:1.2em">&#128187;</span> Reindex Projects
      </button>
      <span id="index-status" style="color:#666;font-size:0.9em"></span>
    </div>
    <div id="index-results" style="display:none;margin-bottom:20px;padding:16px;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);border-left:4px solid #2e7d32">
      <h3 style="font-size:1em;color:#2e7d32;margin-bottom:10px" id="index-results-title">Newly Indexed</h3>
      <div id="index-results-list"></div>
    </div>
    <div id="knowledge-results" style="display:none;margin-bottom:20px;padding:16px;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);border-left:4px solid #1565c0">
      <h3 style="font-size:1em;color:#1565c0;margin-bottom:10px" id="knowledge-results-title">Knowledge Docs</h3>
      <div id="knowledge-results-list"></div>
    </div>
    <div id="project-results" style="display:none;margin-bottom:20px;padding:16px;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);border-left:4px solid #7b1fa2">
      <h3 style="font-size:1em;color:#7b1fa2;margin-bottom:10px" id="project-results-title">Projects</h3>
      <div id="project-results-list"></div>
    </div>
    <div style="margin-bottom:16px">
      <p id="explorer-total" style="font-size:1.1em;font-weight:600;color:#1a1a2e;margin-bottom:4px">Loading...</p>
      <p style="color:#666;font-size:0.85em;margin-bottom:16px">Visual overview of all indexed knowledge in Jarvis</p>
    </div>
    <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:24px">
      <div style="flex:1;min-width:300px;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
        <h3 style="font-size:0.95em;color:#555;margin-bottom:12px">Knowledge Sources</h3>
        <div id="explorer-sources"></div>
      </div>
      <div style="flex:1;min-width:300px;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
        <h3 style="font-size:0.95em;color:#555;margin-bottom:12px">Content Types</h3>
        <div id="explorer-types"></div>
      </div>
    </div>
    <div style="background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);margin-bottom:24px">
      <h3 style="font-size:0.95em;color:#555;margin-bottom:12px">Activity Timeline (last 30 dates)</h3>
      <div id="explorer-timeline" style="display:flex;align-items:flex-end;gap:2px;height:100px;overflow-x:auto"></div>
      <div id="explorer-timeline-labels" style="display:flex;gap:2px;font-size:0.7em;color:#999;overflow-x:auto;margin-top:4px"></div>
    </div>
    <div style="background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
      <h3 style="font-size:0.95em;color:#555;margin-bottom:12px">Top Documents (by chunk count)</h3>
      <div id="explorer-top-titles"></div>
    </div>
  </div>
</div>

  <div id="eval-tab" style="display:none">
    <div style="margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <button onclick="evalSeed()" id="btn-seed" style="padding:10px 22px;background:#7b1fa2;color:white;border:none;border-radius:8px;font-size:0.95em;cursor:pointer;transition:background 0.2s">
        Seed Eval Dataset
      </button>
      <button onclick="evalRun()" id="btn-eval-run" style="padding:10px 22px;background:#2e7d32;color:white;border:none;border-radius:8px;font-size:0.95em;cursor:pointer;transition:background 0.2s">
        Run Evaluation
      </button>
      <select id="eval-k" style="padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:0.95em">
        <option value="3">k=3</option>
        <option value="5" selected>k=5</option>
        <option value="10">k=10</option>
      </select>
      <span id="eval-action-status" style="color:#666;font-size:0.9em"></span>
    </div>

    <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap">
      <div style="flex:1;min-width:200px;background:white;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);text-align:center">
        <div style="font-size:0.85em;color:#666;margin-bottom:4px">Total Chunks</div>
        <div id="eval-total" style="font-size:1.8em;font-weight:700;color:#1a1a2e">—</div>
      </div>
      <div style="flex:1;min-width:200px;background:white;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);text-align:center">
        <div style="font-size:0.85em;color:#666;margin-bottom:4px">Eval Queries</div>
        <div id="eval-queries" style="font-size:1.8em;font-weight:700;color:#7b1fa2">—</div>
      </div>
      <div style="flex:1;min-width:200px;background:white;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);text-align:center">
        <div style="font-size:0.85em;color:#666;margin-bottom:4px">Date Range</div>
        <div id="eval-date-range" style="font-size:1em;font-weight:600;color:#1565c0">—</div>
      </div>
    </div>

    <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap">
      <div style="flex:1;min-width:300px;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
        <h3 style="font-size:0.95em;color:#555;margin-bottom:12px">Source Distribution</h3>
        <div id="eval-sources"></div>
      </div>
      <div style="flex:1;min-width:300px;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
        <h3 style="font-size:0.95em;color:#555;margin-bottom:12px">Content Type Distribution</h3>
        <div id="eval-types"></div>
      </div>
    </div>

    <div id="eval-results-panel" style="display:none;background:white;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);margin-bottom:20px;border-left:4px solid #2e7d32">
      <h3 style="font-size:1.05em;color:#2e7d32;margin-bottom:16px">Evaluation Results</h3>
      <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap">
        <div style="flex:1;min-width:140px;background:#e8f5e9;padding:14px;border-radius:8px;text-align:center">
          <div style="font-size:0.8em;color:#2e7d32;margin-bottom:4px">Precision@k</div>
          <div id="eval-precision" style="font-size:1.5em;font-weight:700;color:#2e7d32">—</div>
          <div style="font-size:0.7em;color:#666;margin-top:6px" title="Of the top-k results returned, how many are actually relevant">How accurate are the results (less noise)</div>
        </div>
        <div style="flex:1;min-width:140px;background:#e3f2fd;padding:14px;border-radius:8px;text-align:center">
          <div style="font-size:0.8em;color:#1565c0;margin-bottom:4px">Recall@k</div>
          <div id="eval-recall" style="font-size:1.5em;font-weight:700;color:#1565c0">—</div>
          <div style="font-size:0.7em;color:#666;margin-top:6px" title="Of all relevant documents, how many were found in top-k">How complete are the results (less missed)</div>
        </div>
        <div style="flex:1;min-width:140px;background:#f3e5f5;padding:14px;border-radius:8px;text-align:center">
          <div style="font-size:0.8em;color:#7b1fa2;margin-bottom:4px">MRR</div>
          <div id="eval-mrr" style="font-size:1.5em;font-weight:700;color:#7b1fa2">—</div>
          <div style="font-size:0.7em;color:#666;margin-top:6px" title="1/position of the first relevant result (1.0 = first result is relevant)">How fast the best result appears</div>
        </div>
      </div>
      <div style="margin-bottom:16px;padding:14px 16px;background:#fafafa;border-radius:8px;border:1px solid #e8e8e8">
        <div style="display:flex;justify-content:space-between;align-items:center;cursor:pointer" onclick="this.parentElement.querySelector('.guide-body').style.display=this.parentElement.querySelector('.guide-body').style.display==='none'?'block':'none'; this.querySelector('.chevron').textContent=this.parentElement.querySelector('.guide-body').style.display==='none'?'\u25b6':'\u25bc'">
          <span style="font-size:0.9em;font-weight:600;color:#555">How to Read These Results</span>
          <span class="chevron" style="color:#999;font-size:0.8em">\u25bc</span>
        </div>
        <div class="guide-body" style="margin-top:12px">
          <table style="width:100%;border-collapse:collapse;font-size:0.85em">
            <thead><tr style="border-bottom:2px solid #e0e0e0">
              <th style="text-align:left;padding:8px;color:#555">What you see</th>
              <th style="text-align:left;padding:8px;color:#555">What it means</th>
            </tr></thead>
            <tbody>
              <tr style="border-bottom:1px solid #f0f0f0">
                <td style="padding:8px"><strong>k=1, P=1.0</strong></td>
                <td style="padding:8px;color:#444">RAG search is <strong>stable</strong> \u2014 the top result is always relevant</td>
              </tr>
              <tr style="border-bottom:1px solid #f0f0f0">
                <td style="padding:8px"><strong>k=5, P&lt;1.0</strong></td>
                <td style="padding:8px;color:#444">Lower-ranked results include <strong>irrelevant content</strong> (noise increases with k)</td>
              </tr>
              <tr style="border-bottom:1px solid #f0f0f0">
                <td style="padding:8px"><strong>Recall goes up with k</strong></td>
                <td style="padding:8px;color:#444">Relevant content is <strong>spread across rankings</strong> \u2014 need more results to find everything</td>
              </tr>
              <tr style="border-bottom:1px solid #f0f0f0">
                <td style="padding:8px"><strong>MRR \u2248 1.0</strong></td>
                <td style="padding:8px;color:#444">The <strong>best result always comes first</strong> \u2014 great ranking quality</td>
              </tr>
              <tr>
                <td style="padding:8px"><strong>Query row is <span style="color:#c62828">red</span></strong></td>
                <td style="padding:8px;color:#444">That query <strong>found no relevant results</strong> \u2014 check if the content is indexed</td>
              </tr>
            </tbody>
          </table>
          <div style="margin-top:10px;padding:10px 12px;background:#fff3e0;border-radius:6px;font-size:0.82em;color:#e65100;border:1px solid #ffcc80">
            <strong>Note:</strong> The eval dataset was auto-generated by the Seed command \u2014 it uses RAG\u2019s own search results as \u201ccorrect answers.\u201d This measures <strong>result stability</strong>, not true accuracy. For real accuracy testing, manually review and edit the relevant_ids in the eval dataset.
          </div>
        </div>
      </div>
      <div id="eval-per-query" style="max-height:400px;overflow-y:auto"></div>
    </div>

    <div style="background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="font-size:0.95em;color:#555;margin:0">Sample Data (first 50 chunks)</h3>
        <div style="display:flex;gap:8px;align-items:center">
          <input type="text" id="eval-view-filter" placeholder="Filter by text or title..."
                 style="padding:6px 12px;border:1px solid #ddd;border-radius:4px;font-size:0.9em;width:200px">
          <select id="eval-view-source" style="padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:0.9em">
            <option value="">All Sources</option>
          </select>
          <button onclick="loadEvalView()" style="padding:6px 16px;background:#4a90d9;color:white;border:none;border-radius:4px;font-size:0.9em;cursor:pointer">Refresh</button>
        </div>
      </div>
      <div id="eval-view-table" style="max-height:500px;overflow-y:auto"></div>
    </div>
  </div>

<script>
function toggleFilters() {
  document.getElementById('filters').classList.toggle('open');
}

function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

document.getElementById('query').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doSearch();
});

async function doSearch() {
  const q = document.getElementById('query').value.trim();
  if (!q) return;
  const loading = document.getElementById('loading');
  const results = document.getElementById('results');
  loading.style.display = 'block';
  results.innerHTML = '';

  const params = new URLSearchParams({
    query: q,
    date_from: document.getElementById('date_from').value,
    date_to: document.getElementById('date_to').value,
    source: document.getElementById('source').value,
    difficulty: document.getElementById('difficulty').value,
    item_type: document.getElementById('item_type').value,
    top_k: document.getElementById('top_k').value,
    min_score: document.getElementById('min_score').value,
  });

  try {
    const resp = await fetch('/api/search?' + params);
    const data = await resp.json();
    loading.style.display = 'none';

    if (!data.results || data.results.length === 0) {
      results.innerHTML = '<div class="no-results">No results found. Try broadening your search.</div>';
      return;
    }

    window._lastQuery = q;
    let pipeHtml = '';
    if (data.pipeline) {
      const p = data.pipeline;
      const stages = (p.stages || []).map(s => `${s.name}: ${s.count} hits (${s.ms}ms)`).join(' &#8594; ');
      let rewriteHtml = '';
      if (p.rewritten_query) {
        let aliasHtml = '';
        if (p.aliases && p.aliases.length > 0) {
          aliasHtml = '<div style="margin-bottom:2px"><b>Aliases:</b> ' +
            p.aliases.map(a => `<span style="display:inline-block;padding:1px 6px;margin:1px 2px;background:#e3f2fd;border-radius:4px;font-family:monospace;font-size:0.9em;color:#1565c0${a.fuzzy ? ';border:1px dashed #90caf9' : ''}">${escHtml(a.original)} &#8594; ${escHtml(a.expanded)}</span>`).join(' ') +
            '</div>';
        }
        rewriteHtml = `<div style="margin-bottom:4px">${aliasHtml}<b>Query Rewrite:</b> <span style="color:#888;text-decoration:line-through">${escHtml(p.original_query)}</span> &#8594; <span style="color:#1a73e8;font-weight:500">${escHtml(p.rewritten_query)}</span></div>`;
      }
      pipeHtml = `<div style="margin-bottom:10px;padding:8px 12px;background:#eef6ff;border:1px solid #c8ddf0;border-radius:6px;font-size:0.82em;color:#456">
        ${rewriteHtml}
        <b>Pipeline:</b> ${stages} | Total: ${p.total_ms}ms
        ${p.reranked ? ' | <span style="color:#2a7">&#10003; Re-ranked</span>' : ''}
        ${p.feedback_applied ? ' | <span style="color:#2a7">&#10003; Feedback</span>' : ''}
      </div>`;
    }
    const confLabel = {high:'High confidence', medium:'Medium confidence', low:'Low confidence'}[data.query_confidence] || '';
    const confClass = {high:'qconf-high', medium:'qconf-medium', low:'qconf-low'}[data.query_confidence] || '';
    const confHtml = data.query_confidence ? `<div class="query-confidence ${confClass}">${confLabel} &mdash; ${data.query_confidence === 'high' ? 'Results are highly relevant' : data.query_confidence === 'medium' ? 'Results may be partially relevant' : 'Results may not match well, try different keywords'}</div>` : '';
    const countHtml = `<div style="margin-bottom:8px;color:#666;font-size:0.9em">${data.total} result${data.total!==1?'s':''} for "<b>${escHtml(data.query)}</b>"</div>`;
    results.innerHTML = pipeHtml + confHtml + countHtml + data.results.map((r, i) => {
      const badgeClass = {news_item:'badge-news', raw_content:'badge-raw', learning_guide:'badge-guide',
        book_chapter:'badge-raw', project_doc:'badge-news', personal_note:'badge-guide', task:'badge-news',
        wiki_page:'badge-raw', code_doc:'badge-raw', ai_integration:'badge-news',
        rest_endpoint:'badge-guide', project_technology:'badge-news', project_readme:'badge-raw',
        config_analysis:'badge-guide', project_summary:'badge-news', project_identity:'badge-news',
        project_dependency:'badge-raw', project_changelog:'badge-raw'}[r.item_type] || '';
      const badgeText = {news_item:'NEWS', raw_content:'RAW', learning_guide:'GUIDE',
        book_chapter:'BOOK', project_doc:'PROJECT', personal_note:'NOTE', task:'TASK',
        wiki_page:'WIKI', code_doc:'CODE', ai_integration:'AI',
        rest_endpoint:'REST', project_technology:'TECH', project_readme:'README',
        config_analysis:'CONFIG', project_summary:'SUMMARY', project_identity:'MAVEN',
        project_dependency:'DEPS', project_changelog:'CHANGELOG'}[r.item_type] || r.item_type;
      const safeUrl = r.url && /^https?:\/\//i.test(r.url) ? r.url : '';
      const link = safeUrl ? `<a href="${escHtml(safeUrl)}" target="_blank">Original</a>` : '';
      const file = r.filename ? `<span style="color:#888;font-size:0.85em"> &middot; ${escHtml(r.filename)}</span>` : '';
      const parent = r.parent_title && r.parent_title !== r.title ? `<span style="color:#888;font-size:0.85em"> from <b>${escHtml(r.parent_title)}</b></span>` : '';
      const preview = r.text.length > 200 ? r.text.substring(0, 200) + '...' : r.text;
      const fullId = `full-${i}`;
      const scoreInfo = [];
      if (r.vector_score !== undefined) scoreInfo.push(`vec:${r.vector_score.toFixed(3)}`);
      if (r.rerank_score !== undefined) scoreInfo.push(`rerank:${r.rerank_score.toFixed(3)}`);
      if (r.feedback_score !== undefined && r.feedback_score !== 0.5) scoreInfo.push(`fb:${r.feedback_score.toFixed(2)}`);
      const scoreDetail = scoreInfo.length ? `<span style="color:#999;font-size:0.8em;margin-left:6px">(${scoreInfo.join(', ')})</span>` : '';
      const confBadge = r.confidence ? `<span class="confidence-badge conf-${r.confidence}">${r.confidence.toUpperCase()}</span>` : '';
      const chunkId = r.id || '';
      return `<div class="result">
        <h3>${i+1}. ${escHtml(r.title)} <span class="score">${r.score.toFixed(3)}</span>${confBadge}${scoreDetail}</h3>
        <div class="meta">
          <span class="badge ${badgeClass}">${badgeText}</span>
          ${escHtml(r.date)} &middot; ${escHtml(r.source)} &middot; ${escHtml(r.difficulty)} ${link} ${file} ${parent}
        </div>
        <div class="preview">${escHtml(preview)}</div>
        <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <a href="#" onclick="toggleChunk('${fullId}');return false" style="color:#4a90d9;font-size:0.9em" id="toggle-${fullId}">Show chunk</a>
          ${r.filename ? `<a href="#" onclick="loadDocument('${r.filename.replace(/'/g,"\\'")}','${(r.parent_title||'').replace(/'/g,"\\'")}','doc-${fullId}');return false" style="color:#4a90d9;font-size:0.9em;margin-left:8px">View full document</a>` : ''}
          <span style="margin-left:auto;display:flex;gap:4px">
            <button onclick="sendFeedback('${chunkId}',${i},'thumbs_up',this)" title="Relevant" style="background:none;border:1px solid #ccc;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:0.85em">👍</button>
            <button onclick="sendFeedback('${chunkId}',${i},'thumbs_down',this)" title="Not relevant" style="background:none;border:1px solid #ccc;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:0.85em">👎</button>
          </span>
        </div>
        <div id="${fullId}" style="display:none;margin-top:8px;padding:12px;background:#f8f9fa;border:1px solid #e0e0e0;border-radius:6px;white-space:pre-wrap;font-size:0.9em;max-height:400px;overflow-y:auto;line-height:1.6">${r.text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
        <div id="doc-${fullId}" style="display:none;margin-top:8px"></div>
      </div>`;
    }).join('');

    // Fetch suggestions when confidence is not high
    if (data.query_confidence && data.query_confidence !== 'high') {
      fetch('/api/suggest?query=' + encodeURIComponent(data.query))
        .then(r => r.json())
        .then(sg => {
          if (sg.suggestions && sg.suggestions.length > 0) {
            const sugDiv = document.createElement('div');
            sugDiv.style.cssText = 'margin-top:12px;padding:12px 16px;background:#f0f7ff;border-radius:8px;border:1px solid #bbdefb';
            sugDiv.innerHTML = '<div style="font-size:0.85em;color:#1565c0;font-weight:600;margin-bottom:6px">Try also:</div>';
            sg.suggestions.forEach(function(s) {
              var a = document.createElement('a');
              a.href = '#';
              a.style.cssText = 'display:inline-block;margin:2px 6px 2px 0;padding:3px 10px;background:white;border:1px solid #90caf9;border-radius:14px;font-size:0.85em;color:#1565c0;text-decoration:none';
              a.textContent = s.text;
              a.onclick = function(e) { e.preventDefault(); document.getElementById('query').value = this.textContent; doSearch(); };
              sugDiv.appendChild(a);
            });
            results.appendChild(sugDiv);
          }
        }).catch(() => {});
    }

    // "Was this helpful?" feedback bar
    if (data.results && data.results.length > 0) {
      window._lastSearchChunkIds = data.results.map(r => r.id).filter(Boolean);
      const fbDiv = document.createElement('div');
      fbDiv.style.cssText = 'margin-top:16px;padding:12px 16px;background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);display:flex;align-items:center;gap:12px;border:1px solid #e0e0e0';
      fbDiv.innerHTML = '<span style="font-size:0.9em;color:#555">Did you find what you needed?</span>' +
        '<button onclick="submitHelpful(true,this.parentElement)" style="padding:4px 14px;background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;color:#2e7d32;cursor:pointer;font-size:0.85em">Yes, helpful</button>' +
        '<button onclick="submitHelpful(false,this.parentElement)" style="padding:4px 14px;background:#fce4ec;border:1px solid #ef9a9a;border-radius:6px;color:#c62828;cursor:pointer;font-size:0.85em">Not quite</button>';
      results.appendChild(fbDiv);
    }
  } catch (err) {
    loading.style.display = 'none';
    results.innerHTML = '<div class="no-results">Error: ' + err.message + '</div>';
  }
}

function toggleChunk(id) {
  const el = document.getElementById(id);
  const btn = document.getElementById('toggle-' + id);
  if (el.style.display === 'none') {
    el.style.display = 'block'; btn.textContent = 'Hide chunk';
    const idx = parseInt((id.match(/\\d+/) || ['0'])[0]);
    fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:window._lastQuery||'',chunk_id:id,action:'expand',position:idx})});
  } else { el.style.display = 'none'; btn.textContent = 'Show chunk'; }
}

function sendFeedback(chunkId, position, action, btn) {
  const weight = action === 'thumbs_up' ? 'view_doc' : 'reformulate';
  fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({query:window._lastQuery||'',chunk_id:chunkId,action:weight,position:position})
  }).then(function(){ btn.style.opacity='0.5'; btn.disabled=true; });
}

function submitHelpful(helpful, container) {
  const ids = window._lastSearchChunkIds || [];
  fetch('/api/feedback/helpful', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({query:window._lastQuery||'', helpful:helpful, chunk_ids:ids.slice(0,5)})
  });
  container.innerHTML = helpful
    ? '<span style="color:#2e7d32;font-size:0.9em">Thanks! Your feedback improves future results.</span>'
    : '<span style="color:#e65100;font-size:0.9em">Thanks! Try rephrasing or check the suggestions above.</span>';
}

function showTab(tab) {
  document.getElementById('search-tab').style.display = tab === 'search' ? 'block' : 'none';
  document.getElementById('library-tab').style.display = tab === 'library' ? 'block' : 'none';
  document.getElementById('analysis-tab').style.display = tab === 'analysis' ? 'block' : 'none';
  document.getElementById('eval-tab').style.display = tab === 'eval' ? 'block' : 'none';
  ['search','library','analysis','eval'].forEach(function(t) {
    var btn = document.getElementById('tab-' + t);
    btn.style.background = t === tab ? '#4a90d9' : 'white';
    btn.style.color = t === tab ? 'white' : '#4a90d9';
  });
  if (tab === 'library') loadLibrary();
  if (tab === 'analysis') { loadAnalysis(); loadExplorer(); }
  if (tab === 'eval') loadEvalStats();
}

function loadAnalysis() {}

async function loadLibrary() {
  const typeFilter = document.getElementById('lib-type').value;
  const container = document.getElementById('library-results');
  container.innerHTML = '<div style="text-align:center;padding:20px;color:#999">Loading...</div>';
  try {
    const params = new URLSearchParams({item_type: typeFilter});
    const resp = await fetch('/api/library?' + params);
    const data = await resp.json();
    document.getElementById('lib-stats').textContent = `${data.total_documents} documents, ${data.total_chunks} chunks`;
    if (!data.documents || data.documents.length === 0) {
      container.innerHTML = '<div class="no-results">No documents found.</div>';
      return;
    }
    container.innerHTML = data.documents.map((doc, i) => {
      const badgeClass = {news_item:'badge-news', raw_content:'badge-raw', learning_guide:'badge-guide',
        book_chapter:'badge-raw', project_doc:'badge-news', personal_note:'badge-guide', task:'badge-news',
        wiki_page:'badge-raw', code_doc:'badge-raw', ai_integration:'badge-news',
        rest_endpoint:'badge-guide', project_technology:'badge-news', project_readme:'badge-raw',
        config_analysis:'badge-guide', project_summary:'badge-news', project_identity:'badge-news',
        project_dependency:'badge-raw', project_changelog:'badge-raw'}[doc.item_type] || '';
      const badgeText = {news_item:'NEWS', raw_content:'RAW', learning_guide:'GUIDE',
        book_chapter:'BOOK', project_doc:'PROJECT', personal_note:'NOTE', task:'TASK',
        wiki_page:'WIKI', code_doc:'CODE', ai_integration:'AI',
        rest_endpoint:'REST', project_technology:'TECH', project_readme:'README',
        config_analysis:'CONFIG', project_summary:'SUMMARY', project_identity:'MAVEN',
        project_dependency:'DEPS', project_changelog:'CHANGELOG'}[doc.item_type] || doc.item_type;
      const docId = `lib-doc-${i}`;
      return `<div class="result">
        <h3>${doc.title} <span class="score">${doc.chunks} chunks</span></h3>
        <div class="meta">
          <span class="badge ${badgeClass}">${badgeText}</span>
          ${doc.date} &middot; ${doc.source} ${doc.filename ? '&middot; ' + doc.filename : ''}
        </div>
        <div style="margin-top:6px;display:flex;gap:12px">
          <a href="#" onclick="loadLibDoc('${doc.filename.replace(/'/g,"\\'")}','${doc.title.replace(/'/g,"\\'")}','${docId}');return false" style="color:#4a90d9;font-size:0.9em">View content</a>
          <a href="#" onclick="deleteDoc('${doc.filename.replace(/'/g,"\\'")}','${doc.title.replace(/'/g,"\\'")}',this.closest('.result'));return false" style="color:#e53935;font-size:0.9em">Delete</a>
        </div>
        <div id="${docId}" style="display:none;margin-top:8px"></div>
      </div>`;
    }).join('');
  } catch (err) {
    container.innerHTML = '<div class="no-results">Error: ' + err.message + '</div>';
  }
}

async function loadLibDoc(filename, title, targetId) {
  const el = document.getElementById(targetId);
  if (el.style.display === 'block') { el.style.display = 'none'; return; }
  el.innerHTML = '<div style="color:#666;padding:8px">Loading...</div>';
  el.style.display = 'block';
  try {
    const params = new URLSearchParams({filename: filename, parent_title: title});
    const resp = await fetch('/api/document?' + params);
    const data = await resp.json();
    if (!data.chunks || data.chunks.length === 0) {
      el.innerHTML = '<div style="color:#999;padding:8px">No content found.</div>';
      return;
    }
    el.innerHTML = `<div style="padding:12px;background:#f0f4f8;border:1px solid #d0d8e0;border-radius:8px;max-height:800px;overflow-y:auto">
      <div style="font-weight:bold;margin-bottom:8px;color:#1a1a2e">${data.parent_title || data.filename} (${data.total_chunks} chunks)</div>
      ${data.chunks.map((c,i) => `<div style="margin-bottom:12px;padding:10px;background:white;border-radius:4px;border-left:3px solid #4a90d9">
        <div style="font-size:0.85em;color:#666;margin-bottom:4px">${c.title}</div>
        <div style="white-space:pre-wrap;font-size:0.9em;line-height:1.6">${c.text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
      </div>`).join('')}
    </div>`;
  } catch (err) {
    el.innerHTML = '<div style="color:red;padding:8px">Error: ' + err.message + '</div>';
  }
}

async function deleteDoc(filename, title, resultEl) {
  if (!confirm(`Delete "${title}"? This removes all chunks for this document from the RAG store.`)) return;
  try {
    const resp = await fetch('/api/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({filename: filename, parent_title: title})
    });
    const data = await resp.json();
    if (data.removed > 0) {
      resultEl.style.opacity = '0.3';
      resultEl.style.pointerEvents = 'none';
      resultEl.querySelector('h3').innerHTML += ' <span style="color:#e53935;font-size:0.8em">(deleted)</span>';
      document.querySelector('.stats').textContent = `Indexed chunks: ${data.remaining}`;
    } else {
      alert('No matching chunks found to delete.');
    }
  } catch (err) {
    alert('Delete failed: ' + err.message);
  }
}

async function indexNew() {
  const btn = document.getElementById('btn-index-new');
  const statusEl = document.getElementById('index-status');
  const resultsBox = document.getElementById('index-results');
  const resultsList = document.getElementById('index-results-list');
  const resultsTitle = document.getElementById('index-results-title');
  if (btn.disabled) return;

  btn.disabled = true;
  btn.style.opacity = '0.6';
  statusEl.textContent = 'Starting indexing...';
  resultsBox.style.display = 'none';

  try {
    const r = await fetch('/api/index-new', { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Failed to start');

    const jobId = d.job_id;
    statusEl.innerHTML = 'Indexing in progress... <span style="display:inline-block;width:14px;height:14px;border:2px solid #2e7d32;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:middle"></span>';

    const poll = setInterval(async function() {
      try {
        const sr = await fetch('/api/index-new/' + encodeURIComponent(jobId));
        const sd = await sr.json();
        if (sd.status === 'done' || sd.status === 'error') {
          clearInterval(poll);
          btn.disabled = false;
          btn.style.opacity = '1';

          if (sd.status === 'done') {
            statusEl.innerHTML = '<span style="color:#2e7d32;font-weight:600">&#10003; ' + (sd.result || 'Done').substring(0, 200) + '</span>';
            if (sd.new_items && sd.new_items.length > 0) {
              resultsTitle.textContent = 'Newly Indexed (' + sd.new_items.length + ' briefing' + (sd.new_items.length > 1 ? 's' : '') + ')';
              resultsList.innerHTML = sd.new_items.map(function(item) {
                const icon = item.error ? '<span style="color:#e53935">&#10007;</span>' : '<span style="color:#2e7d32">&#10003;</span>';
                const detail = item.error
                  ? '<span style="color:#e53935">' + item.error + '</span>'
                  : '<span style="color:#666">' + item.chunks + ' chunks indexed</span>';
                return '<div style="padding:8px 12px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:8px">'
                  + icon
                  + ' <span style="font-weight:600;min-width:100px">' + item.date + '</span> '
                  + detail
                  + '</div>';
              }).join('');
              resultsBox.style.display = 'block';
            }
            loadAnalysis();
          } else {
            statusEl.innerHTML = '<span style="color:#e53935">Error: ' + (sd.result || 'Unknown error').substring(0, 200) + '</span>';
          }
        }
      } catch (pollErr) {
        clearInterval(poll);
        btn.disabled = false;
        btn.style.opacity = '1';
        statusEl.innerHTML = '<span style="color:#e53935">Poll error: ' + pollErr.message + '</span>';
      }
    }, 2000);
  } catch (err) {
    btn.disabled = false;
    btn.style.opacity = '1';
    statusEl.innerHTML = '<span style="color:#e53935">Error: ' + err.message + '</span>';
  }
}

async function refreshKnowledge() {
  const btn = document.getElementById('btn-refresh-knowledge');
  const statusEl = document.getElementById('index-status');
  const resultsBox = document.getElementById('knowledge-results');
  const resultsList = document.getElementById('knowledge-results-list');
  const resultsTitle = document.getElementById('knowledge-results-title');
  if (btn.disabled) return;

  btn.disabled = true;
  btn.style.opacity = '0.6';
  statusEl.textContent = 'Scanning knowledge docs...';
  resultsBox.style.display = 'none';

  try {
    const r = await fetch('/api/refresh-knowledge', { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Failed to start');

    const jobId = d.job_id;
    statusEl.innerHTML = 'Refreshing knowledge docs... <span style="display:inline-block;width:14px;height:14px;border:2px solid #1565c0;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:middle"></span>';

    const poll = setInterval(async function() {
      try {
        const sr = await fetch('/api/refresh-knowledge/' + encodeURIComponent(jobId));
        const sd = await sr.json();
        if (sd.status === 'done' || sd.status === 'error') {
          clearInterval(poll);
          btn.disabled = false;
          btn.style.opacity = '1';

          if (sd.status === 'done') {
            statusEl.innerHTML = '<span style="color:#1565c0;font-weight:600">&#10003; ' + (sd.result || 'Done').substring(0, 200) + '</span>';
            if (sd.new_items && sd.new_items.length > 0) {
              var newCount = sd.new_items.filter(function(x) { return x.new; }).length;
              resultsTitle.textContent = 'Knowledge Docs (' + sd.new_items.length + ' file' + (sd.new_items.length > 1 ? 's' : '') + (newCount > 0 ? ', ' + newCount + ' new' : '') + ')';
              resultsList.innerHTML = sd.new_items.map(function(item) {
                var icon = item.error ? '<span style="color:#e53935">&#10007;</span>'
                  : item.new ? '<span style="color:#1565c0;font-weight:700">NEW</span>'
                  : '<span style="color:#2e7d32">&#10003;</span>';
                var detail = item.error
                  ? '<span style="color:#e53935">' + item.error + '</span>'
                  : '<span style="color:#666">' + item.chunks + ' chunks</span>';
                return '<div style="padding:8px 12px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:8px">'
                  + icon
                  + ' <span style="font-weight:600;min-width:200px">' + item.file + '</span> '
                  + detail
                  + '</div>';
              }).join('');
              resultsBox.style.display = 'block';
            }
            loadAnalysis();
          } else {
            statusEl.innerHTML = '<span style="color:#e53935">Error: ' + (sd.result || 'Unknown error').substring(0, 200) + '</span>';
          }
        }
      } catch (pollErr) {
        clearInterval(poll);
        btn.disabled = false;
        btn.style.opacity = '1';
        statusEl.innerHTML = '<span style="color:#e53935">Poll error: ' + pollErr.message + '</span>';
      }
    }, 2000);
  } catch (err) {
    btn.disabled = false;
    btn.style.opacity = '1';
    statusEl.innerHTML = '<span style="color:#e53935">Error: ' + err.message + '</span>';
  }
}

async function reindexProjects() {
  const btn = document.getElementById('btn-reindex-projects');
  const statusEl = document.getElementById('index-status');
  const resultsBox = document.getElementById('project-results');
  const resultsList = document.getElementById('project-results-list');
  const resultsTitle = document.getElementById('project-results-title');
  if (btn.disabled) return;

  btn.disabled = true;
  btn.style.opacity = '0.6';
  statusEl.textContent = 'Scanning project directories...';
  resultsBox.style.display = 'none';

  try {
    const r = await fetch('/api/reindex-projects', { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Failed to start');

    const jobId = d.job_id;
    statusEl.innerHTML = 'Reindexing projects... <span style="display:inline-block;width:14px;height:14px;border:2px solid #7b1fa2;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:middle"></span>';

    const poll = setInterval(async function() {
      try {
        const sr = await fetch('/api/reindex-projects/' + encodeURIComponent(jobId));
        const sd = await sr.json();
        if (sd.status === 'done' || sd.status === 'error') {
          clearInterval(poll);
          btn.disabled = false;
          btn.style.opacity = '1';

          if (sd.status === 'done') {
            statusEl.innerHTML = '<span style="color:#7b1fa2;font-weight:600">&#10003; ' + (sd.result || 'Done').substring(0, 300) + '</span>';
            if (sd.new_items && sd.new_items.length > 0) {
              resultsTitle.textContent = 'Projects (' + sd.new_items.length + ' project' + (sd.new_items.length > 1 ? 's' : '') + ')';
              resultsList.innerHTML = sd.new_items.map(function(item) {
                var icon = item.error ? '<span style="color:#e53935">&#10007;</span>'
                  : item.skipped ? '<span style="color:#999">&#8212;</span>'
                  : '<span style="color:#7b1fa2">&#10003;</span>';
                var detail = item.error
                  ? '<span style="color:#e53935">' + item.error + '</span>'
                  : item.skipped
                  ? '<span style="color:#999">' + item.skipped + '</span>'
                  : '<span style="color:#666">' + item.chunks + ' chunks' + (item.deduped ? ', ' + item.deduped + ' deduped' : '') + '</span>';
                return '<div style="padding:8px 12px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:8px">'
                  + icon
                  + ' <span style="font-weight:600;min-width:150px">' + item.name + '</span> '
                  + '<span style="color:#aaa;font-size:0.85em;min-width:200px">' + (item.path || '') + '</span> '
                  + detail
                  + '</div>';
              }).join('');
              resultsBox.style.display = 'block';
            }
            loadAnalysis();
          } else {
            statusEl.innerHTML = '<span style="color:#e53935">Error: ' + (sd.result || 'Unknown error').substring(0, 300) + '</span>';
          }
        }
      } catch (pollErr) {
        clearInterval(poll);
        btn.disabled = false;
        btn.style.opacity = '1';
        statusEl.innerHTML = '<span style="color:#e53935">Poll error: ' + pollErr.message + '</span>';
      }
    }, 3000);
  } catch (err) {
    btn.disabled = false;
    btn.style.opacity = '1';
    statusEl.innerHTML = '<span style="color:#e53935">Error: ' + err.message + '</span>';
  }
}

async function loadDocument(filename, parentTitle, targetId) {
  const el = document.getElementById(targetId);
  if (el.style.display === 'block') { el.style.display = 'none'; return; }
  el.innerHTML = '<div style="color:#666;padding:8px">Loading full document...</div>';
  el.style.display = 'block';
  try {
    const params = new URLSearchParams({filename: filename, parent_title: parentTitle});
    const resp = await fetch('/api/document?' + params);
    const data = await resp.json();
    if (!data.chunks || data.chunks.length === 0) {
      el.innerHTML = '<div style="color:#999;padding:8px">No content found.</div>';
      return;
    }
    el.innerHTML = `<div style="padding:12px;background:#f0f4f8;border:1px solid #d0d8e0;border-radius:8px;max-height:800px;overflow-y:auto">
      <div style="font-weight:bold;margin-bottom:8px;color:#1a1a2e">${data.parent_title || data.filename} (${data.total_chunks} chunks)</div>
      ${data.chunks.map((c,i) => `<div style="margin-bottom:12px;padding:10px;background:white;border-radius:4px;border-left:3px solid #4a90d9">
        <div style="font-size:0.85em;color:#666;margin-bottom:4px">${c.title}</div>
        <div style="white-space:pre-wrap;font-size:0.9em;line-height:1.6">${c.text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
      </div>`).join('')}
    </div>`;
  } catch (err) {
    el.innerHTML = '<div style="color:red;padding:8px">Error: ' + err.message + '</div>';
  }
}

async function loadExplorer() {
  const totalEl = document.getElementById('explorer-total');
  totalEl.textContent = 'Loading...';
  try {
    const resp = await fetch('/api/explorer-stats');
    const data = await resp.json();
    totalEl.textContent = data.total + ' chunks indexed';

    const barColors = ['#4a90d9','#2e7d32','#7b1fa2','#e65100','#c62828','#1565c0','#00838f','#4527a0'];

    // Sources
    const srcEl = document.getElementById('explorer-sources');
    const srcEntries = Object.entries(data.by_source).sort((a,b) => b[1] - a[1]);
    const maxSrc = srcEntries[0] ? srcEntries[0][1] : 1;
    srcEl.innerHTML = srcEntries.map((e, i) => {
      const pct = Math.round(e[1] / data.total * 100);
      const w = Math.max(Math.round(e[1] / maxSrc * 100), 2);
      return '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:0.85em;margin-bottom:2px"><span>' + escHtml(e[0]) + '</span><span style="color:#666">' + e[1] + ' (' + pct + '%)</span></div><div style="height:8px;background:#eee;border-radius:4px;overflow:hidden"><div style="height:100%;width:' + w + '%;background:' + barColors[i % barColors.length] + ';border-radius:4px"></div></div></div>';
    }).join('');

    // Types
    const typeEl = document.getElementById('explorer-types');
    const typeEntries = Object.entries(data.by_type).sort((a,b) => b[1] - a[1]);
    const maxType = typeEntries[0] ? typeEntries[0][1] : 1;
    typeEl.innerHTML = typeEntries.map((e, i) => {
      const pct = Math.round(e[1] / data.total * 100);
      const w = Math.max(Math.round(e[1] / maxType * 100), 2);
      return '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:0.85em;margin-bottom:2px"><span>' + escHtml(e[0]) + '</span><span style="color:#666">' + e[1] + ' (' + pct + '%)</span></div><div style="height:8px;background:#eee;border-radius:4px;overflow:hidden"><div style="height:100%;width:' + w + '%;background:' + barColors[(i+3) % barColors.length] + ';border-radius:4px"></div></div></div>';
    }).join('');

    // Timeline
    const timeEl = document.getElementById('explorer-timeline');
    const labelEl = document.getElementById('explorer-timeline-labels');
    const dateEntries = Object.entries(data.by_date).sort((a,b) => a[0].localeCompare(b[0]));
    const maxDate = Math.max(...dateEntries.map(e => e[1]), 1);
    timeEl.innerHTML = dateEntries.map(e => {
      const h = Math.max(Math.round(e[1] / maxDate * 90), 3);
      return '<div title="' + e[0] + ': ' + e[1] + ' chunks" style="flex:1;min-width:12px;height:' + h + 'px;background:#4a90d9;border-radius:2px 2px 0 0;cursor:pointer"></div>';
    }).join('');
    labelEl.innerHTML = dateEntries.map(e => '<div style="flex:1;min-width:12px;text-align:center;white-space:nowrap;overflow:hidden">' + e[0].slice(5) + '</div>').join('');

    // Top titles
    const titlesEl = document.getElementById('explorer-top-titles');
    titlesEl.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:0.88em"><thead><tr style="border-bottom:2px solid #e0e0e0"><th style="text-align:left;padding:6px 10px">Title</th><th style="text-align:right;padding:6px 10px">Chunks</th></tr></thead><tbody>' +
      data.top_titles.map(t => '<tr style="border-bottom:1px solid #f0f0f0"><td style="padding:6px 10px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escHtml(t.title) + '</td><td style="text-align:right;padding:6px 10px;color:#4a90d9;font-weight:600">' + t.count + '</td></tr>').join('') +
      '</tbody></table>';
  } catch (err) {
    totalEl.textContent = 'Error loading explorer: ' + err.message;
  }
}

var _evalStatsLoaded = false;
async function loadEvalStats() {
  if (_evalStatsLoaded) return;
  try {
    const resp = await fetch('/api/eval/stats');
    const data = await resp.json();
    document.getElementById('eval-total').textContent = data.total_chunks.toLocaleString();
    document.getElementById('eval-queries').textContent = data.eval_queries;
    document.getElementById('eval-date-range').textContent = data.date_range || '—';

    const barColors = ['#4a90d9','#2e7d32','#7b1fa2','#e65100','#c62828','#1565c0','#00838f','#4527a0'];
    const srcEl = document.getElementById('eval-sources');
    const srcEntries = Object.entries(data.by_source).sort((a,b) => b[1] - a[1]).slice(0, 12);
    const maxSrc = srcEntries[0] ? srcEntries[0][1] : 1;
    srcEl.innerHTML = srcEntries.map((e, i) => {
      const pct = Math.round(e[1] / data.total_chunks * 100);
      const w = Math.max(Math.round(e[1] / maxSrc * 100), 2);
      return '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:0.85em;margin-bottom:2px"><span>' + escHtml(e[0]) + '</span><span style="color:#666">' + e[1] + ' (' + pct + '%)</span></div><div style="height:6px;background:#eee;border-radius:3px;overflow:hidden"><div style="height:100%;width:' + w + '%;background:' + barColors[i % barColors.length] + ';border-radius:3px"></div></div></div>';
    }).join('');

    const typeEl = document.getElementById('eval-types');
    const typeEntries = Object.entries(data.by_type).sort((a,b) => b[1] - a[1]);
    const maxType = typeEntries[0] ? typeEntries[0][1] : 1;
    typeEl.innerHTML = typeEntries.map((e, i) => {
      const pct = Math.round(e[1] / data.total_chunks * 100);
      const w = Math.max(Math.round(e[1] / maxType * 100), 2);
      return '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:0.85em;margin-bottom:2px"><span>' + escHtml(e[0]) + '</span><span style="color:#666">' + e[1] + ' (' + pct + '%)</span></div><div style="height:6px;background:#eee;border-radius:3px;overflow:hidden"><div style="height:100%;width:' + w + '%;background:' + barColors[(i+3) % barColors.length] + ';border-radius:3px"></div></div></div>';
    }).join('');

    var sel = document.getElementById('eval-view-source');
    srcEntries.forEach(function(e) {
      var o = document.createElement('option');
      o.value = e[0]; o.textContent = e[0] + ' (' + e[1] + ')';
      sel.appendChild(o);
    });

    if (data.last_eval) {
      showEvalResults(data.last_eval);
    }

    loadEvalView();
    _evalStatsLoaded = true;
  } catch (err) {
    document.getElementById('eval-total').textContent = 'Error: ' + err.message;
  }
}

function showEvalResults(evalData) {
  var panel = document.getElementById('eval-results-panel');
  panel.style.display = 'block';
  var m = evalData.metrics || {};
  var k = evalData.k || 5;
  document.getElementById('eval-precision').textContent = (m['precision@' + k] !== undefined) ? m['precision@' + k].toFixed(3) : '—';
  document.getElementById('eval-recall').textContent = (m['recall@' + k] !== undefined) ? m['recall@' + k].toFixed(3) : '—';
  document.getElementById('eval-mrr').textContent = (m.mrr !== undefined) ? m.mrr.toFixed(3) : '—';

  var pq = evalData.per_query || [];
  if (pq.length > 0) {
    var html = '<table style="width:100%;border-collapse:collapse;font-size:0.85em"><thead><tr style="border-bottom:2px solid #e0e0e0"><th style="text-align:left;padding:6px 8px">Query</th><th style="text-align:left;padding:6px 8px">Category</th><th style="text-align:right;padding:6px 8px">P</th><th style="text-align:right;padding:6px 8px">R</th><th style="text-align:right;padding:6px 8px">MRR</th></tr></thead><tbody>';
    pq.forEach(function(q) {
      var color = q.recall > 0 ? '#2e7d32' : '#c62828';
      html += '<tr style="border-bottom:1px solid #f0f0f0"><td style="padding:6px 8px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:' + color + '">' + escHtml(q.query.substring(0, 60)) + '</td>';
      html += '<td style="padding:6px 8px;color:#666">' + escHtml(q.category || '') + '</td>';
      html += '<td style="text-align:right;padding:6px 8px">' + q.precision.toFixed(2) + '</td>';
      html += '<td style="text-align:right;padding:6px 8px">' + q.recall.toFixed(2) + '</td>';
      html += '<td style="text-align:right;padding:6px 8px">' + q.mrr.toFixed(2) + '</td></tr>';
    });
    html += '</tbody></table>';
    document.getElementById('eval-per-query').innerHTML = html;
  }
}

async function evalSeed() {
  var btn = document.getElementById('btn-seed');
  var st = document.getElementById('eval-action-status');
  btn.disabled = true; btn.style.opacity = '0.6';
  st.textContent = 'Seeding eval dataset...';
  try {
    const resp = await fetch('/api/eval/seed', {method: 'POST'});
    const data = await resp.json();
    if (data.job_id) {
      pollEvalJob(data.job_id, 'seed', btn, st);
    } else {
      st.textContent = data.error || 'Seed failed';
      btn.disabled = false; btn.style.opacity = '1';
    }
  } catch (err) {
    st.textContent = 'Error: ' + err.message;
    btn.disabled = false; btn.style.opacity = '1';
  }
}

async function evalRun() {
  var btn = document.getElementById('btn-eval-run');
  var st = document.getElementById('eval-action-status');
  var k = document.getElementById('eval-k').value;
  btn.disabled = true; btn.style.opacity = '0.6';
  st.textContent = 'Running evaluation (k=' + k + ')...';
  try {
    const resp = await fetch('/api/eval/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({k: parseInt(k)})
    });
    const data = await resp.json();
    if (data.job_id) {
      pollEvalJob(data.job_id, 'eval', btn, st);
    } else {
      st.textContent = data.error || 'Eval failed';
      btn.disabled = false; btn.style.opacity = '1';
    }
  } catch (err) {
    st.textContent = 'Error: ' + err.message;
    btn.disabled = false; btn.style.opacity = '1';
  }
}

function pollEvalJob(jobId, kind, btn, statusEl) {
  var interval = setInterval(async function() {
    try {
      const resp = await fetch('/api/eval/job/' + jobId);
      const data = await resp.json();
      if (data.status === 'done') {
        clearInterval(interval);
        statusEl.textContent = data.message || 'Done';
        btn.disabled = false; btn.style.opacity = '1';
        if (kind === 'eval' && data.report) {
          showEvalResults(data.report);
        }
        _evalStatsLoaded = false;
        loadEvalStats();
      } else if (data.status === 'error') {
        clearInterval(interval);
        statusEl.textContent = 'Error: ' + (data.message || 'Unknown error');
        btn.disabled = false; btn.style.opacity = '1';
      } else {
        statusEl.textContent = data.message || 'Running...';
      }
    } catch (err) {
      clearInterval(interval);
      statusEl.textContent = 'Poll error: ' + err.message;
      btn.disabled = false; btn.style.opacity = '1';
    }
  }, 2000);
}

async function loadEvalView() {
  var filter = (document.getElementById('eval-view-filter').value || '').trim();
  var source = document.getElementById('eval-view-source').value;
  var params = new URLSearchParams({limit: '50'});
  if (filter) params.set('query', filter);
  if (source) params.set('source', source);
  try {
    const resp = await fetch('/api/eval/view?' + params);
    const data = await resp.json();
    var chunks = data.chunks || [];
    var html = '<table style="width:100%;border-collapse:collapse;font-size:0.85em"><thead><tr style="border-bottom:2px solid #e0e0e0"><th style="text-align:left;padding:6px 8px">#</th><th style="text-align:left;padding:6px 8px">Title</th><th style="text-align:left;padding:6px 8px">Source</th><th style="text-align:left;padding:6px 8px">Type</th><th style="text-align:left;padding:6px 8px">Date</th><th style="text-align:left;padding:6px 8px">Preview</th></tr></thead><tbody>';
    chunks.forEach(function(c, i) {
      html += '<tr style="border-bottom:1px solid #f0f0f0">';
      html += '<td style="padding:6px 8px;color:#999">' + (i+1) + '</td>';
      html += '<td style="padding:6px 8px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escHtml((c.title || '').substring(0, 50)) + '</td>';
      html += '<td style="padding:6px 8px;color:#666;font-size:0.9em">' + escHtml(c.source || '') + '</td>';
      html += '<td style="padding:6px 8px"><span style="display:inline-block;padding:1px 6px;border-radius:8px;background:#e3f2fd;color:#1565c0;font-size:0.8em">' + escHtml(c.item_type || '') + '</span></td>';
      html += '<td style="padding:6px 8px;color:#666;font-size:0.9em;white-space:nowrap">' + escHtml(c.date || '') + '</td>';
      html += '<td style="padding:6px 8px;color:#888;font-size:0.85em;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escHtml((c.text || '').substring(0, 100)) + '</td>';
      html += '</tr>';
    });
    html += '</tbody></table>';
    if (chunks.length === 0) html = '<div style="padding:20px;text-align:center;color:#999">No chunks found</div>';
    document.getElementById('eval-view-table').innerHTML = html;
  } catch (err) {
    document.getElementById('eval-view-table').innerHTML = '<div style="color:#c62828">Error: ' + err.message + '</div>';
  }
}
</script>
</body>
</html>"""


def _get_model():
    global _model
    if _model is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            local_files_only=True,
            model_kwargs={"local_files_only": True},
            tokenizer_kwargs={"local_files_only": True},
        )
    return _model


def _get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        _client = QdrantClient(":memory:")
        _client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        if os.path.exists(SNAPSHOT_PATH):
            with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            points = data.get("points", [])
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = [
                    PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                    for p in points[i:i + batch_size]
                ]
                _client.upsert(collection_name=COLLECTION, points=batch)
            print(f"  Loaded {len(points)} points from snapshot", flush=True)
    return _client


def get_stats() -> str:
    if not os.path.exists(SNAPSHOT_PATH):
        return "No indexed data yet. Run index_briefing.py first."
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return f"Indexed chunks: {data.get('count', 0)}"
    except Exception as e:
        return f"Error: {e}"


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, stats=get_stats())


@app.route("/api/search")
def api_search():
    from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"results": [], "error": "Empty query"})

    original_query = query
    rewritten_query = None

    from query_rewrite import smart_rewrite
    rewrite_result = smart_rewrite(query)
    effective = rewrite_result.effective_query
    if effective != query:
        rewritten_query = effective
        query = effective

    model = _get_model()
    client = _get_client()
    embedding = model.encode(query).tolist()

    conditions = []
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    source = request.args.get("source", "").strip()
    difficulty = request.args.get("difficulty", "")
    item_type = request.args.get("item_type", "")
    try:
        top_k = int(request.args.get("top_k", "10"))
    except (TypeError, ValueError):
        top_k = 10
    top_k = max(1, min(top_k, 100))
    try:
        min_score = float(request.args.get("min_score", "0.5"))
    except (TypeError, ValueError):
        min_score = 0.5
    min_score = max(0.0, min(min_score, 1.0))

    if date_from:
        conditions.append(FieldCondition(key="date", range=Range(gte=date_from)))
    if date_to:
        conditions.append(FieldCondition(key="date", range=Range(lte=date_to)))
    if source:
        conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
    if difficulty:
        conditions.append(FieldCondition(key="difficulty", match=MatchValue(value=difficulty)))
    if item_type:
        conditions.append(FieldCondition(key="item_type", match=MatchValue(value=item_type)))

    query_filter = Filter(must=conditions) if conditions else None

    import time as _time
    aliases_info = [
        {"original": a.original, "expanded": a.expanded, "type": a.alias_type, "fuzzy": a.fuzzy}
        for a in rewrite_result.aliases
    ] if rewrite_result.aliases else []
    pipeline_info = {"stages": [], "vector_count": 0, "bm25_count": 0,
                     "reranked": False, "feedback_applied": False,
                     "original_query": original_query,
                     "rewritten_query": rewritten_query,
                     "aliases": aliases_info}
    t0 = _time.time()

    vector_limit = max(top_k * 3, 20)
    response = client.query_points(
        collection_name=COLLECTION,
        query=embedding,
        query_filter=query_filter,
        limit=vector_limit,
        score_threshold=min_score,
        with_payload=True,
    )

    vector_results = []
    for hit in response.points:
        p = hit.payload
        vector_results.append({
            "id": str(hit.id),
            "title": p.get("title", "Untitled"),
            "date": p.get("date", ""),
            "source": p.get("source", ""),
            "difficulty": p.get("difficulty", ""),
            "item_type": p.get("item_type", ""),
            "url": p.get("url", ""),
            "text": p.get("text", ""),
            "score": hit.score,
            "vector_score": hit.score,
            "filename": p.get("filename", ""),
            "parent_title": p.get("parent_title", ""),
        })
    pipeline_info["vector_count"] = len(vector_results)
    pipeline_info["stages"].append({"name": "Vector Search", "count": len(vector_results),
                                     "ms": int((_time.time() - t0) * 1000)})

    # --- BM25 hybrid fusion ---
    t1 = _time.time()
    try:
        from bm25_index import bm25_search
        bm25_hits = bm25_search(query, top_k=vector_limit)
        pipeline_info["bm25_count"] = len(bm25_hits)
        if bm25_hits:
            rrf_scores: dict[str, float] = {}
            rrf_data: dict[str, dict] = {}
            k = 60
            for rank, r in enumerate(vector_results):
                rid = r["id"]
                rrf_scores[rid] = rrf_scores.get(rid, 0) + 1.0 / (k + rank + 1)
                rrf_data[rid] = r
            for rank, (pid, _bscore, payload) in enumerate(bm25_hits):
                pid_s = str(pid)
                rrf_scores[pid_s] = rrf_scores.get(pid_s, 0) + 1.0 / (k + rank + 1)
                if pid_s not in rrf_data:
                    rrf_data[pid_s] = {
                        "id": pid_s,
                        "title": payload.get("title", "Untitled"),
                        "date": payload.get("date", ""),
                        "source": payload.get("source", ""),
                        "difficulty": payload.get("difficulty", ""),
                        "item_type": payload.get("item_type", ""),
                        "url": payload.get("url", ""),
                        "text": payload.get("text", ""),
                        "score": 0.0,
                        "vector_score": 0.0,
                        "filename": payload.get("filename", ""),
                        "parent_title": payload.get("parent_title", ""),
                    }
            fused = sorted(rrf_scores.items(), key=lambda x: -x[1])
            vector_results = [rrf_data[rid] for rid, _ in fused if rid in rrf_data]
            pipeline_info["stages"].append({"name": "BM25 + RRF Fusion", "count": len(bm25_hits),
                                             "ms": int((_time.time() - t1) * 1000)})
    except ImportError:
        pass

    # --- Cross-encoder re-ranking (top 20 -> top_k) ---
    t2 = _time.time()
    try:
        from reranker import rerank as _rerank
    except ImportError:
        _rerank = None
    if _rerank is not None and len(vector_results) > top_k:
        rerank_pool = vector_results[:20]
        try:
            reranked = _rerank(query, rerank_pool, top_k=top_k)
            vector_results = reranked
            if any(r.get("rerank_score") is not None for r in reranked):
                pipeline_info["reranked"] = True
                pipeline_info["stages"].append({
                    "name": "Cross-Encoder Rerank",
                    "count": len(rerank_pool),
                    "ms": int((_time.time() - t2) * 1000),
                })
        except Exception:
            traceback.print_exc()
            vector_results = vector_results[:top_k]

    # --- Feedback-weighted ranking ---
    try:
        from feedback_store import get_chunk_score
        fb_applied = False
        for r in vector_results:
            rid = r.get("id", "")
            fb_score = get_chunk_score(rid)
            r["feedback_score"] = round(fb_score, 3)
            if fb_score != 0.5:
                orig = r.get("score", 0)
                r["score"] = 0.8 * orig + 0.2 * fb_score
                fb_applied = True
        if fb_applied:
            vector_results.sort(key=lambda x: -x.get("score", 0))
            pipeline_info["feedback_applied"] = True
    except ImportError:
        pass

    pipeline_info["total_ms"] = int((_time.time() - t0) * 1000)
    results = vector_results[:top_k]

    # --- Confidence scoring ---
    for r in results:
        s = r.get("score", 0)
        if s >= 0.55:
            r["confidence"] = "high"
        elif s >= 0.35:
            r["confidence"] = "medium"
        else:
            r["confidence"] = "low"

    scores = [r.get("score", 0) for r in results]
    top_score = scores[0] if scores else 0
    avg_score = sum(scores) / len(scores) if scores else 0
    if top_score >= 0.55 and avg_score >= 0.35:
        query_confidence = "high"
    elif top_score >= 0.35:
        query_confidence = "medium"
    else:
        query_confidence = "low"

    return jsonify({"results": results, "query": query, "total": len(results),
                    "pipeline": pipeline_info,
                    "query_confidence": query_confidence})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Record a user interaction event for feedback-weighted ranking."""
    try:
        from feedback_store import record_event
        data = request.get_json() or {}
        record_event(
            query=data.get("query", ""),
            chunk_id=data.get("chunk_id", ""),
            action=data.get("action", ""),
            position=data.get("position", 0),
        )
        return jsonify({"recorded": True})
    except ImportError:
        return jsonify({"recorded": False, "error": "feedback_store not available"})


@app.route("/api/feedback/helpful", methods=["POST"])
def api_feedback_helpful():
    """Record explicit 'was this helpful?' feedback for a search query."""
    try:
        from feedback_store import record_eval_candidate, record_event
        data = request.get_json() or {}
        query = data.get("query", "")
        helpful = data.get("helpful", True)
        chunk_ids = data.get("chunk_ids", [])
        if not isinstance(chunk_ids, list):
            return jsonify({"recorded": False, "error": "chunk_ids must be a list"}), 400

        for cid in chunk_ids[:5]:
            record_eval_candidate(query, str(cid), helpful)
            action = "view_doc" if helpful else "reformulate"
            record_event(query, str(cid), action, position=0)

        return jsonify({"recorded": True, "count": len(chunk_ids[:5])})
    except ImportError:
        return jsonify({"recorded": False, "error": "feedback_store not available"})
    except Exception as e:
        return jsonify({"recorded": False, "error": str(e)}), 500


@app.route("/api/document")
def api_document():
    """Return all chunks from a document, ordered by chunk index."""
    filename = request.args.get("filename", "").strip()
    parent_title = request.args.get("parent_title", "").strip()
    if not filename and not parent_title:
        return jsonify({"error": "Provide filename or parent_title", "chunks": []})

    client = _get_client()
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    conditions = []
    if filename:
        conditions.append(FieldCondition(key="filename", match=MatchValue(value=filename)))
    if parent_title:
        conditions.append(FieldCondition(key="parent_title", match=MatchValue(value=parent_title)))

    result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=conditions),
        limit=500,
        with_payload=True,
    )
    points, _ = result

    chunks = []
    for p in points:
        chunks.append({
            "title": p.payload.get("title", ""),
            "text": p.payload.get("text", ""),
            "item_type": p.payload.get("item_type", ""),
            "date": p.payload.get("date", ""),
        })

    return jsonify({
        "filename": filename,
        "parent_title": parent_title,
        "total_chunks": len(chunks),
        "chunks": chunks,
    })


@app.route("/api/chunk-analysis")
def api_chunk_analysis():
    """Chunk breakdown by source and type."""
    client = _get_client()
    by_source = {}
    by_type = {}
    total = 0
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
        )
        points, next_offset = result
        for p in points:
            total += 1
            pl = p.payload or {}
            src = str(pl.get("source") or "(unknown)")
            it = str(pl.get("item_type") or "(unknown)")
            by_source[src] = by_source.get(src, 0) + 1
            by_type[it] = by_type.get(it, 0) + 1
        if next_offset is None:
            break
        offset = next_offset
    return jsonify({"total": total, "by_source": by_source, "by_type": by_type})


@app.route("/api/suggest")
def api_suggest():
    """Suggest similar/related queries based on nearby chunk titles."""
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"suggestions": []})

    try:
        model = _get_model()
        embedding = model.encode(query).tolist()
        client = _get_client()

        response = client.query_points(
            collection_name=COLLECTION,
            query=embedding,
            limit=20,
            score_threshold=0.15,
        )
        points = response.points if hasattr(response, "points") else response

        seen = set()
        suggestions = []
        query_lower = query.lower()
        for p in points:
            pl = p.payload or {}
            title = str(pl.get("title") or "")
            if not title or title.lower() == query_lower:
                continue
            key = title.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({
                "text": title,
                "source": str(pl.get("source") or ""),
                "item_type": str(pl.get("item_type") or ""),
            })
            if len(suggestions) >= 5:
                break

        return jsonify({"suggestions": suggestions})
    except Exception:
        return jsonify({"suggestions": []})


@app.route("/api/explorer-stats")
def api_explorer_stats():
    """Rich stats for Data Explorer: counts, date distribution, top titles."""
    client = _get_client()
    by_source = {}
    by_type = {}
    by_date = {}
    top_titles = {}
    total = 0
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
        )
        points, next_offset = result
        for p in points:
            total += 1
            pl = p.payload or {}
            src = str(pl.get("source") or "(unknown)")
            it = str(pl.get("item_type") or "(unknown)")
            dt = str(pl.get("date") or "unknown")[:10]
            title = str(pl.get("title") or "(untitled)")
            by_source[src] = by_source.get(src, 0) + 1
            by_type[it] = by_type.get(it, 0) + 1
            by_date[dt] = by_date.get(dt, 0) + 1
            top_titles[title] = top_titles.get(title, 0) + 1
        if next_offset is None:
            break
        offset = next_offset

    sorted_dates = sorted(by_date.items(), key=lambda x: x[0], reverse=True)[:30]
    sorted_titles = sorted(top_titles.items(), key=lambda x: -x[1])[:20]
    return jsonify({
        "total": total,
        "by_source": by_source,
        "by_type": by_type,
        "by_date": dict(sorted_dates),
        "top_titles": [{"title": t, "count": c} for t, c in sorted_titles],
    })


@app.route("/api/library")
def api_library():
    """List all indexed documents grouped by parent_title/filename."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    item_type = request.args.get("item_type", "").strip()
    client = _get_client()

    conditions = []
    if item_type:
        conditions.append(FieldCondition(key="item_type", match=MatchValue(value=item_type)))
    query_filter = Filter(must=conditions) if conditions else None

    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=query_filter,
            limit=500,
            offset=offset,
            with_payload=True,
        )
        points, next_offset = result
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    docs = {}
    for p in all_points:
        key = p.payload.get("parent_title") or p.payload.get("filename") or p.payload.get("title", "Untitled")
        if key not in docs:
            docs[key] = {
                "title": key,
                "date": p.payload.get("date", ""),
                "source": p.payload.get("source", ""),
                "item_type": p.payload.get("item_type", ""),
                "filename": p.payload.get("filename", ""),
                "chunks": 0,
            }
        docs[key]["chunks"] += 1

    doc_list = sorted(docs.values(), key=lambda d: (d["date"], d["title"]), reverse=True)
    return jsonify({
        "documents": doc_list,
        "total_documents": len(doc_list),
        "total_chunks": len(all_points),
    })


@app.route("/api/delete", methods=["POST"])
def api_delete():
    """Delete all chunks matching a filename or parent_title from the store."""
    data = request.get_json() or {}
    filename = data.get("filename", "").strip()
    parent_title = data.get("parent_title", "").strip()

    if not filename and not parent_title:
        return jsonify({"error": "Provide filename or parent_title", "removed": 0})

    if not os.path.exists(SNAPSHOT_PATH):
        return jsonify({"error": "No snapshot file", "removed": 0})

    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        snap = json.load(f)

    before = len(snap["points"])
    snap["points"] = [
        p for p in snap["points"]
        if not _matches_delete(p["payload"], filename, parent_title)
    ]
    after = len(snap["points"])
    removed = before - after

    if removed > 0:
        snap["count"] = after
        _tmp = f"{SNAPSHOT_PATH}.tmp-{os.getpid()}"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        os.replace(_tmp, SNAPSHOT_PATH)

        global _client
        _client = None

    return jsonify({"removed": removed, "remaining": after})


def _matches_delete(payload: dict, filename: str, parent_title: str) -> bool:
    if filename and payload.get("filename", "") == filename:
        if parent_title and payload.get("parent_title", "") == parent_title:
            return True
        if not parent_title:
            return True
    if parent_title and not filename:
        return payload.get("parent_title", "") == parent_title
    return False


def _run_index_new(job_id: str) -> None:
    """Index NEW briefing date folders not yet in the RAG store. Runs in a background thread."""
    status = "error"
    msg = ""
    new_items = []
    try:
        client = _get_client()
        existing_dates: set[str] = set()
        offset = None
        while True:
            result = client.scroll(
                collection_name=COLLECTION, limit=500, offset=offset,
                with_payload=["date", "source"], with_vectors=False,
            )
            points, next_offset = result
            for p in points:
                src = p.payload.get("source", "")
                if src in ("PDF Briefing", "learning-guide") or src.startswith("arxiv") or src.startswith("techcrunch"):
                    d = p.payload.get("date", "")
                    if d:
                        existing_dates.add(d)
            if next_offset is None:
                break
            offset = next_offset

        all_dates = sorted(
            d for d in os.listdir(REPORTS_ROOT)
            if os.path.isdir(os.path.join(REPORTS_ROOT, d))
            and re.match(r"\d{4}-\d{2}-\d{2}", d)
        )
        new_dates = [d for d in all_dates if d not in existing_dates]

        if not new_dates:
            status = "done"
            msg = f"No new briefings to index. {len(all_dates)} folders already indexed."
        else:
            rag_dir = SCRIPT_DIR
            sys.path.insert(0, rag_dir)
            from index_briefing import index_date_folder, _save_snapshot
            model = _get_model()
            total_chunks = 0
            for date_folder_name in new_dates:
                folder_path = os.path.join(REPORTS_ROOT, date_folder_name)
                try:
                    count = index_date_folder(folder_path, client, model)
                    total_chunks += count
                    new_items.append({"date": date_folder_name, "chunks": count})
                except Exception as e:
                    msg += f"\n  Error indexing {date_folder_name}: {e}"
                    new_items.append({"date": date_folder_name, "chunks": 0, "error": str(e)})

            _save_snapshot(client)
            global _client
            _client = None

            status = "done"
            msg = f"Indexed {len(new_dates)} new briefing(s) ({total_chunks} chunks). Skipped {len(existing_dates)} already indexed."
    except Exception as e:
        msg = f"Error: {e}\n{traceback.format_exc()}"
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j:
            j["status"] = status
            j["result"] = msg
            j["new_items"] = new_items


@app.route("/api/index-new", methods=["POST"])
def api_index_new():
    """Start indexing new briefing folders in a background thread."""
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "started": time.time(),
            "result": "",
            "new_items": [],
        }
    threading.Thread(target=_run_index_new, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/index-new/<job_id>")
def api_index_new_status(job_id: str):
    """Poll the status of an index-new job."""
    with _jobs_lock:
        j = _jobs.get(job_id)
    if not j:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": j["status"],
        "result": j["result"],
        "new_items": j.get("new_items", []),
    })


def _run_refresh_knowledge(job_id: str) -> None:
    """Re-index all documents under the knowledge/ folder. Runs in a background thread."""
    status = "error"
    msg = ""
    new_items = []
    try:
        if not os.path.isdir(KNOWLEDGE_ROOT):
            status = "error"
            msg = f"Knowledge folder not found: {KNOWLEDGE_ROOT}"
        else:
            rag_dir = SCRIPT_DIR
            sys.path.insert(0, rag_dir)
            from index_custom import index_file, _save_snapshot as _save_snap_custom

            client = _get_client()
            model = _get_model()

            existing_knowledge = set()
            offset = None
            while True:
                result = client.scroll(
                    collection_name=COLLECTION, limit=500, offset=offset,
                    with_payload=["source", "filename"], with_vectors=False,
                )
                points, next_offset = result
                for p in points:
                    src = p.payload.get("source", "")
                    if src.startswith("knowledge") or src == "custom":
                        fn = p.payload.get("filename", "")
                        if fn:
                            existing_knowledge.add(fn)
                if next_offset is None:
                    break
                offset = next_offset

            total_chunks = 0
            total_files = 0
            new_files = 0
            for root, _, files in os.walk(KNOWLEDGE_ROOT):
                for fname in sorted(files):
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in (".md", ".markdown", ".txt", ".pdf"):
                        continue
                    fpath = os.path.join(root, fname)
                    total_files += 1
                    try:
                        count = index_file(fpath, client, model)
                        total_chunks += count
                        is_new = fname not in existing_knowledge
                        if is_new:
                            new_files += 1
                        rel = os.path.relpath(fpath, KNOWLEDGE_ROOT).replace("\\", "/")
                        new_items.append({"file": rel, "chunks": count, "new": is_new})
                    except Exception as e:
                        rel = os.path.relpath(fpath, KNOWLEDGE_ROOT).replace("\\", "/")
                        new_items.append({"file": rel, "chunks": 0, "error": str(e)})

            _save_snap_custom(client)
            global _client
            _client = None

            status = "done"
            msg = f"Scanned {total_files} files ({new_files} new), {total_chunks} chunks total."
    except Exception as e:
        msg = f"Error: {e}\n{traceback.format_exc()}"
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j:
            j["status"] = status
            j["result"] = msg
            j["new_items"] = new_items


@app.route("/api/refresh-knowledge", methods=["POST"])
def api_refresh_knowledge():
    """Start re-indexing knowledge documents in a background thread."""
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "started": time.time(),
            "result": "",
            "new_items": [],
        }
    threading.Thread(target=_run_refresh_knowledge, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/refresh-knowledge/<job_id>")
def api_refresh_knowledge_status(job_id: str):
    """Poll the status of a refresh-knowledge job."""
    with _jobs_lock:
        j = _jobs.get(job_id)
    if not j:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": j["status"],
        "result": j["result"],
        "new_items": j.get("new_items", []),
    })


def _run_reindex_projects(job_id: str) -> None:
    """Re-index all configured project directories. Runs in a background thread."""
    status = "error"
    msg = ""
    new_items = []
    try:
        rag_dir = SCRIPT_DIR
        sys.path.insert(0, rag_dir)
        from index_codebase import (
            load_project_dirs, index_project, _save_snapshot as _save_snap_code,
        )

        client = _get_client()
        model = _get_model()

        projects = load_project_dirs()
        total_chunks = 0
        total_projects = 0
        seen_hashes: set[str] = set()

        for proj in projects:
            name = proj["name"]
            path = proj["path"]
            if not os.path.isdir(path):
                new_items.append({"name": name, "path": path, "chunks": 0,
                                  "skipped": "path not found"})
                continue
            try:
                count, deduped_count = index_project(name, path, model, client, seen_hashes)
                total_chunks += count
                total_projects += 1
                new_items.append({"name": name, "path": path, "chunks": count,
                                  "deduped": deduped_count})
            except Exception as e:
                new_items.append({"name": name, "path": path, "chunks": 0,
                                  "error": str(e)})

        _save_snap_code(client)
        global _client
        _client = None

        try:
            from project_graph import build_graph, save_graph
            graph = build_graph()
            save_graph(graph)
        except Exception as eg:
            new_items.append({"name": "Project Graph", "path": "-",
                              "chunks": 0, "error": f"graph build: {eg}"})

        status = "done"
        msg = (f"Indexed {total_projects} projects ({total_chunks} chunks). "
               f"{len(seen_hashes)} unique files tracked for deduplication.")
    except Exception as e:
        msg = f"Error: {e}\n{traceback.format_exc()}"
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j:
            j["status"] = status
            j["result"] = msg
            j["new_items"] = new_items


@app.route("/api/reindex-projects", methods=["POST"])
def api_reindex_projects():
    """Start re-indexing project directories in a background thread."""
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "started": time.time(),
            "result": "",
            "new_items": [],
        }
    threading.Thread(target=_run_reindex_projects, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/reindex-projects/<job_id>")
def api_reindex_projects_status(job_id: str):
    """Poll the status of a reindex-projects job."""
    with _jobs_lock:
        j = _jobs.get(job_id)
    if not j:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": j["status"],
        "result": j["result"],
        "new_items": j.get("new_items", []),
    })


@app.route("/api/project-config")
def api_project_config():
    """Return current project configuration."""
    if not os.path.isfile(PROJECT_DIRS_PATH):
        return jsonify({"error": "Config not found", "path": PROJECT_DIRS_PATH})
    try:
        with open(PROJECT_DIRS_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return jsonify({"config": cfg, "path": PROJECT_DIRS_PATH})
    except Exception as e:
        return jsonify({"error": str(e), "path": PROJECT_DIRS_PATH})


# ---------------------------------------------------------------------------
# RAG Evaluation API endpoints
# ---------------------------------------------------------------------------

_eval_jobs: dict[str, dict] = {}
_eval_jobs_lock = threading.Lock()

EVAL_SAVE_PATH = os.path.join(REPORTS_ROOT, "eval-dataset")
EVAL_REPORT_PATH = os.path.join(REPORTS_ROOT, "eval-report.json")


@app.route("/api/eval/stats")
def api_eval_stats():
    """Return RAG store stats plus eval dataset info for the eval tab."""
    client = _get_client()
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0
    dates: list[str] = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION, limit=500, offset=offset,
            with_payload=True, with_vectors=False,
        )
        points, next_offset = result
        for p in points:
            total += 1
            pl = p.payload or {}
            src = str(pl.get("source") or "(unknown)")
            it = str(pl.get("item_type") or "(unknown)")
            dt = str(pl.get("date") or "")
            by_source[src] = by_source.get(src, 0) + 1
            by_type[it] = by_type.get(it, 0) + 1
            if dt:
                dates.append(dt[:10])
        if next_offset is None:
            break
        offset = next_offset

    date_range = ""
    if dates:
        date_range = f"{min(dates)} — {max(dates)}"

    eval_queries = 0
    try:
        if os.path.isdir(EVAL_SAVE_PATH):
            from datasets import Dataset as _HFDataset
            ds = _HFDataset.load_from_disk(EVAL_SAVE_PATH)
            eval_queries = len(ds)
    except Exception:
        pass

    last_eval = None
    if os.path.isfile(EVAL_REPORT_PATH):
        try:
            with open(EVAL_REPORT_PATH, "r", encoding="utf-8") as f:
                last_eval = json.load(f)
        except Exception:
            pass

    return jsonify({
        "total_chunks": total,
        "by_source": by_source,
        "by_type": by_type,
        "date_range": date_range,
        "eval_queries": eval_queries,
        "last_eval": last_eval,
    })


@app.route("/api/eval/view")
def api_eval_view():
    """Return a sample of chunks for browsing in the eval tab."""
    source_filter = request.args.get("source", "").strip()
    query_filter = request.args.get("query", "").strip().lower()
    try:
        limit = int(request.args.get("limit", "50"))
    except (TypeError, ValueError):
        limit = 50

    client = _get_client()
    chunks = []
    offset = None

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    conditions = []
    if source_filter:
        conditions.append(FieldCondition(key="source", match=MatchValue(value=source_filter)))
    q_filter = Filter(must=conditions) if conditions else None

    while len(chunks) < limit:
        result = client.scroll(
            collection_name=COLLECTION, limit=200, offset=offset,
            with_payload=True, with_vectors=False,
            scroll_filter=q_filter,
        )
        points, next_offset = result
        for p in points:
            if len(chunks) >= limit:
                break
            pl = p.payload or {}
            if query_filter:
                text = (str(pl.get("text") or "") + " " + str(pl.get("title") or "")).lower()
                if query_filter not in text:
                    continue
            chunks.append({
                "id": str(p.id),
                "title": str(pl.get("title") or ""),
                "source": str(pl.get("source") or ""),
                "item_type": str(pl.get("item_type") or ""),
                "date": str(pl.get("date") or ""),
                "text": str(pl.get("text") or "")[:200],
            })
        if next_offset is None:
            break
        offset = next_offset

    return jsonify({"chunks": chunks, "count": len(chunks)})


def _run_eval_seed(job_id: str) -> None:
    """Background: seed evaluation dataset."""
    status = "error"
    message = ""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from rag_engine import get_qdrant, vector_search
        get_qdrant()

        seed_path = os.path.join(
            os.path.dirname(os.path.dirname(SCRIPT_DIR)),
            "data", "eval", "eval-seed.json",
        )
        if not os.path.isfile(seed_path):
            status = "error"
            message = f"Seed file not found: {seed_path}"
        else:
            from eval_dataset import create_eval_dataset, add_eval_example, EvalExample
            with open(seed_path, "r", encoding="utf-8") as f:
                seeds = json.load(f)
            ds = create_eval_dataset()
            for seed in seeds:
                results = vector_search(seed["query"], top_k=3)
                candidate_ids = [r["id"] for r in results] if results else []
                ids = seed["relevant_ids"] if seed.get("relevant_ids") else candidate_ids
                ds = add_eval_example(ds, EvalExample(
                    query=seed["query"],
                    relevant_ids=ids,
                    answer=seed.get("answer", ""),
                    category=seed.get("category", ""),
                    difficulty=seed.get("difficulty", "medium"),
                    notes=seed.get("notes", ""),
                ))
            ds.save_to_disk(EVAL_SAVE_PATH)
            status = "done"
            message = f"Seeded {len(ds)} eval queries from {len(seeds)} seeds"
    except Exception as e:
        message = f"Error: {e}"
    with _eval_jobs_lock:
        j = _eval_jobs.get(job_id)
        if j:
            j["status"] = status
            j["message"] = message


def _run_eval(job_id: str, k: int = 5) -> None:
    """Background: run evaluation and save report."""
    status = "error"
    message = ""
    report = None
    try:
        if not os.path.isdir(EVAL_SAVE_PATH):
            status = "error"
            message = "No eval dataset. Run 'Seed' first."
        else:
            from datasets import Dataset as _HFDataset
            from eval_runner import run_evaluation
            from rag_engine import get_qdrant, vector_search

            get_qdrant()
            eval_ds = _HFDataset.load_from_disk(EVAL_SAVE_PATH)

            def search_fn(query, top_k=5):
                return vector_search(query, top_k=top_k)

            eval_report = run_evaluation(eval_ds, search_fn, k=k)
            report = eval_report.to_dict()
            eval_report.save(EVAL_REPORT_PATH)
            pk = report["metrics"].get(f"precision@{k}", 0)
            rk = report["metrics"].get(f"recall@{k}", 0)
            m = report["metrics"].get("mrr", 0)
            status = "done"
            message = f"Evaluated {len(eval_ds)} queries: P@{k}={pk:.3f}, R@{k}={rk:.3f}, MRR={m:.3f}"
    except Exception as e:
        message = f"Error: {e}"
    with _eval_jobs_lock:
        j = _eval_jobs.get(job_id)
        if j:
            j["status"] = status
            j["message"] = message
            if report:
                j["report"] = report


@app.route("/api/eval/seed", methods=["POST"])
def api_eval_seed():
    job_id = str(uuid.uuid4())[:8]
    with _eval_jobs_lock:
        _eval_jobs[job_id] = {"status": "running", "message": "Seeding..."}
    threading.Thread(target=_run_eval_seed, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/eval/run", methods=["POST"])
def api_eval_run():
    data = request.get_json(silent=True) or {}
    k = data.get("k", 5)
    job_id = str(uuid.uuid4())[:8]
    with _eval_jobs_lock:
        _eval_jobs[job_id] = {"status": "running", "message": f"Running eval (k={k})..."}
    threading.Thread(target=_run_eval, args=(job_id, k), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/eval/job/<job_id>")
def api_eval_job_status(job_id: str):
    with _eval_jobs_lock:
        j = _eval_jobs.get(job_id)
    if not j:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(j)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18888
    print(f"Starting AI Briefing RAG Search on http://127.0.0.1:{port}", flush=True)
    print("Preloading model and data...", flush=True)
    _get_model()
    _get_client()
    print("Ready! Open your browser.", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False)
