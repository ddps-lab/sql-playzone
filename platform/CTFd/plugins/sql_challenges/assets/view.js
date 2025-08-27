CTFd._internal.challenge.data = undefined;

// TODO: Remove in CTFd v4.0
CTFd._internal.challenge.renderer = null;

CTFd._internal.challenge.preRender = function() {
    // Make modal wider for SQL challenges
    setTimeout(function() {
        var modalDialog = document.querySelector('.modal-dialog');
        if (modalDialog) {
            modalDialog.classList.add('modal-xl');
        }
    }, 10);
};

// TODO: Remove in CTFd v4.0
CTFd._internal.challenge.render = null;

// Function to initialize CodeMirror
function initSQLEditor() {
    var textarea = document.getElementById('challenge-input');
    var container = document.getElementById('sql-editor-container');
    
    if (!textarea || !container) {
        console.log('SQL Editor: Elements not found, retrying...');
        return false;
    }
    
    // Clean up existing editor if any
    if (window.sqlEditor) {
        try {
            window.sqlEditor.toTextArea();
        } catch(e) {}
        window.sqlEditor = null;
    }
    container.innerHTML = '';
    
    // Check if CodeMirror is available
    if (typeof CodeMirror === 'undefined') {
        console.log('SQL Editor: CodeMirror not loaded, loading from CDN...');
        
        // Load CSS if not already loaded
        if (!document.querySelector('link[href*="codemirror"]')) {
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.css';
            document.head.appendChild(link);
            
            var theme = document.createElement('link');
            theme.rel = 'stylesheet';
            theme.href = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/theme/monokai.min.css';
            document.head.appendChild(theme);
        }
        
        // Load JS if not already loading
        if (!window.CodeMirrorLoading) {
            window.CodeMirrorLoading = true;
            
            var script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.js';
            script.onload = function() {
                console.log('SQL Editor: CodeMirror loaded, loading SQL mode...');
                
                var sqlMode = document.createElement('script');
                sqlMode.src = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/mode/sql/sql.min.js';
                sqlMode.onload = function() {
                    console.log('SQL Editor: SQL mode loaded');
                    window.CodeMirrorLoading = false;
                    
                    // Try to initialize again
                    setTimeout(initSQLEditor, 100);
                };
                document.head.appendChild(sqlMode);
            };
            script.onerror = function() {
                console.error('SQL Editor: Failed to load CodeMirror');
                window.CodeMirrorLoading = false;
            };
            document.head.appendChild(script);
        }
        return false;
    }
    
    console.log('SQL Editor: Initializing CodeMirror');
    
    try {
        // Create CodeMirror instance
        var editor = CodeMirror(container, {
            value: textarea.value || '',
            mode: 'text/x-sql',
            theme: 'monokai',
            lineNumbers: true,
            indentUnit: 4,
            lineWrapping: true,
            autofocus: true,
            extraKeys: {
                "Ctrl-Enter": function() {
                    document.getElementById('challenge-submit').click();
                }
            }
        });
        
        // Keep textarea in sync with CodeMirror
        editor.on('change', function(cm) {
            textarea.value = cm.getValue();
            // Trigger Alpine.js update for x-model
            var event = new Event('input', { bubbles: true });
            textarea.dispatchEvent(event);
        });
        
        // Store editor instance
        window.sqlEditor = editor;
        
        // Refresh editor layout after modal animation
        setTimeout(function() {
            if (window.sqlEditor) {
                window.sqlEditor.refresh();
            }
        }, 500);
        
        console.log('SQL Editor: Successfully initialized');
        return true;
        
    } catch(e) {
        console.error('SQL Editor: Error initializing', e);
        return false;
    }
}

// Function to create HTML table from JSON data
function createTable(jsonStr) {
    try {
        var data = JSON.parse(jsonStr);
        if (!data.columns || !data.rows) {
            return '<pre class="p-3 rounded border">' + jsonStr + '</pre>';
        }
        
        if (data.row_count === 0) {
            return '<div class="text-muted p-4 text-center"><i class="fas fa-inbox fa-2x mb-2"></i><br>No rows returned</div>';
        }
        
        var html = '<table class="table table-hover table-sm mb-0">';
        
        // Header
        html += '<thead class="table-dark"><tr>';
        for (var i = 0; i < data.columns.length; i++) {
            html += '<th class="text-white">' + data.columns[i] + '</th>';
        }
        html += '</tr></thead>';
        
        // Body
        html += '<tbody>';
        for (var i = 0; i < data.rows.length; i++) {
            html += '<tr>';
            for (var j = 0; j < data.rows[i].length; j++) {
                var cellValue = data.rows[i][j];
                // Check if the value looks like a flag
                if (typeof cellValue === 'string' && cellValue.match(/^FLAG\{.*\}$/)) {
                    html += '<td class="text-success font-weight-bold">' + cellValue + '</td>';
                } else {
                    html += '<td>' + cellValue + '</td>';
                }
            }
            html += '</tr>';
        }
        html += '</tbody>';
        html += '</table>';
        
        // Add row count info (no hardcoded background)
        html += '<div class="text-muted small p-2 border-top">';
        html += '<i class="fas fa-info-circle"></i> ';
        html += data.row_count + ' row' + (data.row_count !== 1 ? 's' : '') + ' returned';
        html += '</div>';
        
        return html;
    } catch (e) {
        return '<pre class="p-3 rounded border">' + jsonStr + '</pre>';
    }
}

// Function to display SQL results
function displaySQLResults(message, status) {
    // Remove the structured data tags and extract results
    var userMatch = message.match(/\[USER_RESULT\]([\s\S]*?)\[\/USER_RESULT\]/);
    var expectedMatch = message.match(/\[EXPECTED_RESULT\]([\s\S]*?)\[\/EXPECTED_RESULT\]/);
    
    // Handle already solved
    if (status === 'already_solved') {
        message = message.replace(' but you already solved this', '');
    }
    
    // Create result HTML
    var resultHtml = '';
    
    // Status message
    var statusMsg = message.split('\n')[0];
    statusMsg = statusMsg.replace(/\[USER_RESULT\][\s\S]*?\[\/USER_RESULT\]/g, '');
    statusMsg = statusMsg.replace(/\[EXPECTED_RESULT\][\s\S]*?\[\/EXPECTED_RESULT\]/g, '');
    
    if (status === 'already_solved') {
        statusMsg += ' (Already solved)';
    }
    
    // Build custom result display
    resultHtml += '<div class="mt-3">';
    
    // User result
    if (userMatch) {
        var userResult = userMatch[1].trim();
        var tableHtml = createTable(userResult);
        
        var headerClass = 'bg-primary';
        var iconClass = 'fas fa-code';
        if (status === 'correct') {
            headerClass = 'bg-success';
            iconClass = 'fas fa-check-circle';
        } else if (status === 'already_solved') {
            headerClass = 'bg-info';
            iconClass = 'fas fa-info-circle';
        } else if (status === 'incorrect') {
            headerClass = 'bg-danger';
            iconClass = 'fas fa-times-circle';
        }
        
        resultHtml += '<div class="card mb-2 border-0 shadow-sm">';
        resultHtml += '<div class="card-header ' + headerClass + ' text-white border-0">';
        resultHtml += '<h6 class="mb-0"><i class="' + iconClass + '"></i> Your Query Result</h6>';
        resultHtml += '</div>';
        resultHtml += '<div class="card-body p-0">';
        resultHtml += '<div class="table-responsive" style="max-height: 400px; overflow-y: auto;">';
        resultHtml += tableHtml;
        resultHtml += '</div>';
        resultHtml += '</div>';
        resultHtml += '</div>';
    }
    

    
    resultHtml += '</div>';
    
    // Return modified message
    return statusMsg + resultHtml;
}

CTFd._internal.challenge.postRender = function() {
    console.log('SQL Challenge: postRender called');
    
    // Ensure modal is wide
    var modalDialog = document.querySelector('.modal-dialog');
    if (modalDialog) {
        modalDialog.classList.add('modal-xl');
    }
    
    // Try to initialize editor with retries
    var retryCount = 0;
    var maxRetries = 10;
    
    function tryInit() {
        if (initSQLEditor()) {
            console.log('SQL Editor: Initialization successful');
        } else if (retryCount < maxRetries) {
            retryCount++;
            console.log('SQL Editor: Retry ' + retryCount + '/' + maxRetries);
            setTimeout(tryInit, 200);
        } else {
            console.error('SQL Editor: Failed to initialize after ' + maxRetries + ' retries');
            // Show textarea as fallback
            var textarea = document.getElementById('challenge-input');
            if (textarea) {
                textarea.style.display = 'block';
            }
        }
    }
    
    // Start initialization after a short delay to ensure DOM is ready
    setTimeout(tryInit, 100);
    
    // For core-beta theme, override Alpine component
    setTimeout(function() {
        var challengeEl = document.querySelector('[x-data*="Challenge"]');
        if (challengeEl) {
            // Prefer Alpine internal $data if available
            var alpineCtx = challengeEl.__x && challengeEl.__x.$data ? challengeEl.__x.$data : null;
            var component = alpineCtx || (challengeEl._x_dataStack ? challengeEl._x_dataStack[0] : null);
        }
        if (challengeEl && component) {
            console.log('Found Alpine component, overriding renderSubmissionResponse');
            
            // Helper to format alert if it contains SQL structured result
            var tryFormatAlert = function(currentResponse) {
                var alertContainer = document.querySelector('.notification-row .alert');
                if (!alertContainer) return false;
                var strongEl = alertContainer.querySelector('strong');
                if (!strongEl) return false;
                var text = strongEl.textContent || '';
                if (text.indexOf('[USER_RESULT]') === -1) return false;
                
                // Decide message/status
                var message = currentResponse && currentResponse.data ? currentResponse.data.message : text;
                var status = currentResponse && currentResponse.data ? currentResponse.data.status : 'correct';
                
                // Prevent Alpine from resetting text and set clean status
                if (strongEl.hasAttribute('x-text')) strongEl.removeAttribute('x-text');
                var cleanMsg = message.split('\n')[0]
                    .replace(/\[USER_RESULT\][\s\S]*?\[\/USER_RESULT\]/g, '')
                    .replace(/\[EXPECTED_RESULT\][\s\S]*?\[\/EXPECTED_RESULT\]/g, '');
                if (status === 'already_solved') {
                    cleanMsg = cleanMsg.replace(' but you already solved this', '') + ' (Already solved)';
                }
                strongEl.textContent = cleanMsg;
                
                // Ensure result container exists and inject only results portion
                var resultContainer = alertContainer.querySelector('#sql-result-container');
                if (!resultContainer) {
                    resultContainer = document.createElement('div');
                    resultContainer.id = 'sql-result-container';
                    resultContainer.className = 'mt-2';
                    var nextBlock = alertContainer.querySelector('div[x-show]');
                    if (nextBlock) alertContainer.insertBefore(resultContainer, nextBlock);
                    else alertContainer.appendChild(resultContainer);
                }
                var formatted = displaySQLResults(message, status);
                var marker = '<div class="mt-3">';
                var onlyResults = formatted.indexOf(marker) !== -1 ? formatted.slice(formatted.indexOf(marker)) : formatted;
                resultContainer.innerHTML = onlyResults;
                return true;
            };

            // Store and override renderSubmissionResponse on the actual Alpine data object if possible
            var targetObj = challengeEl.__x && challengeEl.__x.$data ? challengeEl.__x.$data : component;
            var originalRender = targetObj.renderSubmissionResponse;

            targetObj.renderSubmissionResponse = async function() {
                console.log('SQL renderSubmissionResponse called');
                if (originalRender) {
                    await originalRender.call(this);
                }
                // Wait for Alpine to paint, then format
                this.$nextTick(() => {
                    setTimeout(() => {
                        var ok = tryFormatAlert(this.response);
                        if (!ok) console.log('SQL formatter: alert not ready yet');
                    }, 50);
                });
            };

            // Also mirror override on other reference if both exist
            if (alpineCtx && component && alpineCtx !== component) {
                component.renderSubmissionResponse = targetObj.renderSubmissionResponse;
            }

            // MutationObserver fallback: watch alert for incoming [USER_RESULT]
            try {
                var alertHost = document.querySelector('.notification-row');
                if (alertHost) {
                    var observer = new MutationObserver(function(mutations) {
                        for (var i = 0; i < mutations.length; i++) {
                            var m = mutations[i];
                            if (m.type === 'childList' || m.type === 'characterData' || m.type === 'subtree') {
                                var alertContainer = document.querySelector('.notification-row .alert');
                                if (!alertContainer) continue;
                                var strongEl = alertContainer.querySelector('strong');
                                if (!strongEl) continue;
                                if (strongEl.textContent && strongEl.textContent.indexOf('[USER_RESULT]') !== -1) {
                                    if (tryFormatAlert(targetObj.response)) {
                                        console.log('SQL formatter: applied via MutationObserver');
                                    }
                                }
                            }
                        }
                    });
                    observer.observe(alertHost, { childList: true, subtree: true, characterData: true });
                }
            } catch(e) {
                console.warn('SQL formatter: MutationObserver setup failed', e);
            }
        } else {
            console.log('Alpine component not found, trying alternative approach');
            // Alternative approach: use MutationObserver to watch for DOM changes
            var observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(function(node) {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                var alerts = node.querySelectorAll ? node.querySelectorAll('.alert strong') : [];
                                for (var i = 0; i < alerts.length; i++) {
                                    var alert = alerts[i];
                                    if (alert.textContent && alert.textContent.indexOf('[USER_RESULT]') !== -1) {
                                        console.log('Found alert via MutationObserver, replacing content');
                                        var messageMatch = alert.textContent.match(/\[USER_RESULT\]([\s\S]*?)\[\/USER_RESULT\]/);
                                        var fakeMessage = alert.textContent;
                                        if (messageMatch) {
                                            fakeMessage = alert.textContent; // use full text for displaySQLResults
                                        }
                                        alert.innerHTML = displaySQLResults(fakeMessage, 'correct');
                                    }
                                }
                            }
                        });
                    }
                });
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    }, 500);
};

CTFd._internal.challenge.submit = function(preview) {
  var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
  var submission = CTFd.lib.$("#challenge-input").val();
  
  // Get value from CodeMirror if it exists
  if (window.sqlEditor) {
      submission = window.sqlEditor.getValue();
  }

  var body = {
    challenge_id: challenge_id,
    submission: submission
  };
  var params = {};
  if (preview) {
    params["preview"] = true;
  }

  return CTFd.api.post_challenge_attempt(params, body).then(function(response) {
    if (response.status === 429) {
      // User was ratelimited but process response
      return response;
    }
    if (response.status === 403) {
      // User is not logged in or CTF is paused.
      return response;
    }
    return response;
  });
};

// Clean up when modal closes
if (typeof jQuery !== 'undefined') {
    jQuery(document).on('hidden.bs.modal', '#challenge-window', function() {
        console.log('SQL Editor: Modal closed, cleaning up');
        if (window.sqlEditor) {
            try {
                window.sqlEditor.toTextArea();
            } catch(e) {}
            window.sqlEditor = null;
        }
        var container = document.getElementById('sql-editor-container');
        if (container) {
            container.innerHTML = '';
        }
    });
}