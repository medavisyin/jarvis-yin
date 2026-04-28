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
    <button onclick="showTab('analysis')" id="tab-analysis" style="padding:8px 20px;border:2px solid #4a90d9;background:white;color:#4a90d9;border-radius:6px;cursor:pointer;font-size:0.95em">Chunk Analysis</button>
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
      <p id="analysis-total" style="font-size:1.1em;font-weight:600;color:#1a1a2e;margin-bottom:16px">Loading...</p>
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div style="flex:1;min-width:300px">
          <h3 style="font-size:0.95em;color:#555;margin-bottom:8px">By Source</h3>
          <table id="analysis-source-table" style="width:100%;border-collapse:collapse;font-size:0.9em">
            <thead><tr style="border-bottom:2px solid #e0e0e0"><th style="text-align:left;padding:8px 12px">Source</th><th style="text-align:right;padding:8px 12px">Count</th><th style="text-align:right;padding:8px 12px">%</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <div style="flex:1;min-width:300px">
          <h3 style="font-size:0.95em;color:#555;margin-bottom:8px">By Type</h3>
          <table id="analysis-type-table" style="width:100%;border-collapse:collapse;font-size:0.9em">
            <thead><tr style="border-bottom:2px solid #e0e0e0"><th style="text-align:left;padding:8px 12px">Type</th><th style="text-align:right;padding:8px 12px">Count</th><th style="text-align:right;padding:8px 12px">%</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
function toggleFilters() {
  document.getElementById('filters').classList.toggle('open');
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
        rewriteHtml = `<div style="margin-bottom:4px"><b>Query Rewrite:</b> <span style="color:#888;text-decoration:line-through">${p.original_query}</span> &#8594; <span style="color:#1a73e8;font-weight:500">${p.rewritten_query}</span></div>`;
      }
      pipeHtml = `<div style="margin-bottom:10px;padding:8px 12px;background:#eef6ff;border:1px solid #c8ddf0;border-radius:6px;font-size:0.82em;color:#456">
        ${rewriteHtml}
        <b>Pipeline:</b> ${stages} | Total: ${p.total_ms}ms
        ${p.reranked ? ' | <span style="color:#2a7">&#10003; Re-ranked</span>' : ''}
        ${p.feedback_applied ? ' | <span style="color:#2a7">&#10003; Feedback</span>' : ''}
      </div>`;
    }
    const countHtml = `<div style="margin-bottom:8px;color:#666;font-size:0.9em">${data.total} result${data.total!==1?'s':''} for "<b>${data.query}</b>"</div>`;
    results.innerHTML = pipeHtml + countHtml + data.results.map((r, i) => {
      const badgeClass = {news_item:'badge-news', raw_content:'badge-raw', learning_guide:'badge-guide',
        book_chapter:'badge-raw', project_doc:'badge-news', personal_note:'badge-guide', task:'badge-news',
        wiki_page:'badge-raw', code_doc:'badge-raw'}[r.item_type] || '';
      const badgeText = {news_item:'NEWS', raw_content:'RAW', learning_guide:'GUIDE',
        book_chapter:'BOOK', project_doc:'PROJECT', personal_note:'NOTE', task:'TASK',
        wiki_page:'WIKI', code_doc:'CODE'}[r.item_type] || r.item_type;
      const link = r.url ? `<a href="${r.url}" target="_blank">Original</a>` : '';
      const file = r.filename ? `<span style="color:#888;font-size:0.85em"> &middot; ${r.filename}</span>` : '';
      const parent = r.parent_title && r.parent_title !== r.title ? `<span style="color:#888;font-size:0.85em"> from <b>${r.parent_title}</b></span>` : '';
      const preview = r.text.length > 200 ? r.text.substring(0, 200) + '...' : r.text;
      const fullId = `full-${i}`;
      const scoreInfo = [];
      if (r.vector_score !== undefined) scoreInfo.push(`vec:${r.vector_score.toFixed(3)}`);
      if (r.rerank_score !== undefined) scoreInfo.push(`rerank:${r.rerank_score.toFixed(3)}`);
      if (r.feedback_score !== undefined && r.feedback_score !== 0.5) scoreInfo.push(`fb:${r.feedback_score.toFixed(2)}`);
      const scoreDetail = scoreInfo.length ? `<span style="color:#999;font-size:0.8em;margin-left:6px">(${scoreInfo.join(', ')})</span>` : '';
      const chunkId = r.id || '';
      return `<div class="result">
        <h3>${i+1}. ${r.title} <span class="score">${r.score.toFixed(3)}</span>${scoreDetail}</h3>
        <div class="meta">
          <span class="badge ${badgeClass}">${badgeText}</span>
          ${r.date} &middot; ${r.source} &middot; ${r.difficulty} ${link} ${file} ${parent}
        </div>
        <div class="preview">${preview}</div>
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

function showTab(tab) {
  document.getElementById('search-tab').style.display = tab === 'search' ? 'block' : 'none';
  document.getElementById('library-tab').style.display = tab === 'library' ? 'block' : 'none';
  document.getElementById('analysis-tab').style.display = tab === 'analysis' ? 'block' : 'none';
  ['search','library','analysis'].forEach(function(t) {
    var btn = document.getElementById('tab-' + t);
    btn.style.background = t === tab ? '#4a90d9' : 'white';
    btn.style.color = t === tab ? 'white' : '#4a90d9';
  });
  if (tab === 'library') loadLibrary();
  if (tab === 'analysis') loadAnalysis();
}

async function loadAnalysis() {
  var totalEl = document.getElementById('analysis-total');
  totalEl.textContent = 'Loading...';
  document.querySelector('#analysis-source-table tbody').innerHTML = '';
  document.querySelector('#analysis-type-table tbody').innerHTML = '';
  try {
    var resp = await fetch('/api/chunk-analysis');
    var data = await resp.json();
    totalEl.textContent = 'Total chunks: ' + data.total.toLocaleString();
    fillAnalysisTable('analysis-source-table', data.by_source, data.total);
    fillAnalysisTable('analysis-type-table', data.by_type, data.total);
  } catch (err) {
    totalEl.textContent = 'Error: ' + err.message;
  }
}

function fillAnalysisTable(tableId, obj, total) {
  var tb = document.querySelector('#' + tableId + ' tbody');
  if (!tb) return;
  var entries = Object.entries(obj || {}).sort(function(a,b) { return b[1] - a[1]; });
  entries.forEach(function(e) {
    var pct = total ? (100 * e[1] / total).toFixed(1) : '0';
    var bar = '<div style="background:#e3f2fd;border-radius:3px;height:6px;margin-top:2px"><div style="background:#4a90d9;border-radius:3px;height:6px;width:' + pct + '%"></div></div>';
    var tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid #f0f0f0';
    tr.innerHTML = '<td style="padding:8px 12px">' + e[0] + bar + '</td><td style="text-align:right;padding:8px 12px;font-weight:600">' + e[1].toLocaleString() + '</td><td style="text-align:right;padding:8px 12px;color:#666">' + pct + '%</td>';
    tb.appendChild(tr);
  });
}

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
        wiki_page:'badge-raw', code_doc:'badge-raw'}[doc.item_type] || '';
      const badgeText = {news_item:'NEWS', raw_content:'RAW', learning_guide:'GUIDE',
        book_chapter:'BOOK', project_doc:'PROJECT', personal_note:'NOTE', task:'TASK',
        wiki_page:'WIKI', code_doc:'CODE'}[doc.item_type] || doc.item_type;
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
</script>
</body>
</html>"""


def _get_model():
    global _model
    if _model is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
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

    vague_signals = ["that thing", "the stuff", "what's", "something about",
                     "you know", "the other", "last time", "earlier", "before"]
    q_lower = query.lower()
    should_rewrite = len(query.split()) < 5 or any(v in q_lower for v in vague_signals)

    if should_rewrite:
        try:
            import requests as _rq
            rw_resp = _rq.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "qwen3:1.7b",
                    "messages": [
                        {"role": "user", "content": (
                            "Rewrite this vague search query into a clear, specific search phrase. "
                            "Reply with ONLY the improved query, nothing else.\n\n"
                            f"Original: {query}\nImproved:"
                        )},
                    ],
                    "stream": False,
                    "options": {"num_predict": 30, "num_ctx": 128},
                    "think": False,
                },
                timeout=10,
            )
            if rw_resp.ok:
                rw_text = rw_resp.json().get("message", {}).get("content", "").strip().strip('"').strip("'")
                rw_text = rw_text.split("\n")[0].strip()[:500]
                if (rw_text and len(rw_text) > 5
                        and rw_text.lower() != query.lower()
                        and "/" not in rw_text):
                    rewritten_query = rw_text
                    query = rw_text
        except Exception:
            pass

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
    pipeline_info = {"stages": [], "vector_count": 0, "bm25_count": 0,
                     "reranked": False, "feedback_applied": False,
                     "original_query": original_query,
                     "rewritten_query": rewritten_query}
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
    return jsonify({"results": results, "query": query, "total": len(results),
                    "pipeline": pipeline_info})


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
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snap, f)

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


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18888
    print(f"Starting AI Briefing RAG Search on http://127.0.0.1:{port}", flush=True)
    print("Preloading model and data...", flush=True)
    _get_model()
    _get_client()
    print("Ready! Open your browser.", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False)
