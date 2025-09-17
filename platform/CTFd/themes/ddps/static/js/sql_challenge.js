
let sqlEditor = null;

// Initialize SQL Editor
function initSQLEditor() {
    const textarea = document.getElementById('challenge-input');
    const container = document.getElementById('sql-editor-container');
    
    if (!textarea || !container) {
        // SQL Editor elements not found
        return false;
    }
    
    // Clean up existing editor if any
    if (sqlEditor) {
        try {
            sqlEditor.toTextArea();
        } catch(e) {}
        sqlEditor = null;
    }
    container.innerHTML = '';
    
    // Check if CodeMirror is available
    if (typeof CodeMirror === 'undefined') {
        // Loading CodeMirror from CDN
        
        // Load CSS
        if (!document.querySelector('link[href*="codemirror"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.css';
            document.head.appendChild(link);
            
            const theme = document.createElement('link');
            theme.rel = 'stylesheet';
            theme.href = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/theme/monokai.min.css';
            document.head.appendChild(theme);
        }
        
        // Load JS
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.js';
        script.onload = function() {
            const sqlMode = document.createElement('script');
            sqlMode.src = 'https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/mode/sql/sql.min.js';
            sqlMode.onload = function() {
                initSQLEditor();
            };
            document.head.appendChild(sqlMode);
        };
        document.head.appendChild(script);
        return false;
    }
    
    // Wait for CTFd object to be ready
    if (typeof CTFd === 'undefined' || !CTFd.user) {
        setTimeout(() => initSQLEditor(), 100);
        return false;
    }
    
    // Get unique storage key with user ID and challenge ID
    const challengeId = document.getElementById('challenge-id').value;
    const userId = CTFd.user.id || 'anonymous';
    const storageKey = `sql-challenge-user${userId}-ch${challengeId}-code`;
    
    // Load saved code from localStorage
    const savedCode = localStorage.getItem(storageKey);
    const initialValue = savedCode || textarea.value || '';
    
    // Create CodeMirror instance WITHOUT initial value
    sqlEditor = CodeMirror(container, {
        value: '',  // Start with empty
        mode: 'text/x-sql',
        theme: 'monokai',
        lineNumbers: true,
        indentUnit: 4,
        lineWrapping: true,
        autofocus: true,
        scrollbarStyle: 'native',
        viewportMargin: Infinity,
        readOnly: false,  // Ensure editor is not read-only
        inputStyle: 'contenteditable',  // Use contenteditable for better compatibility
        extraKeys: {
            "Ctrl-Enter": function() {
                document.getElementById('challenge-submit').click();
            },
            "Tab": "indentMore"
        }
    });
    
    // Force CodeMirror to fit container and load saved code after it's ready
    setTimeout(() => {
        sqlEditor.refresh();
        
        // NOW load the saved code after editor is ready
        if (initialValue) {
            sqlEditor.setValue(initialValue);
        }
        
        sqlEditor.focus();
        // Set cursor to end of content
        sqlEditor.setCursor(sqlEditor.lineCount(), 0);
    }, 200);
    
    // Add click event to focus editor
    container.addEventListener('click', function(e) {
        if (e.target === container || e.target.classList.contains('CodeMirror-scroll')) {
            sqlEditor.focus();
        }
    });
    
    // Save function
    const saveToStorage = function() {
        const content = sqlEditor.getValue();
        textarea.value = content;
        
        if (content.trim()) {
            try {
                localStorage.setItem(storageKey, content);
            } catch (e) {
                console.error('Failed to save:', e);
            }
        } else {
            localStorage.removeItem(storageKey);
        }
    };
    
    // Track initial load to prevent duplicate save
    let skipNextSave = true;
    
    // Listen to ALL input events
    sqlEditor.on('beforeChange', function() {
        if (skipNextSave) {
            skipNextSave = false;
            return;
        }
        // Schedule save immediately after change
        setTimeout(saveToStorage, 0);
    });
    
    // Also save on these events for redundancy
    sqlEditor.on('inputRead', saveToStorage);
    sqlEditor.on('keyHandled', saveToStorage);
    sqlEditor.on('blur', saveToStorage);
    
    // Save every 1 second as backup
    setInterval(() => {
        if (sqlEditor && document.querySelector('.CodeMirror-focused')) {
            saveToStorage();
        }
    }, 1000);
    
    // Show notification if code was restored
    if (savedCode) {
        showAutoSaveNotification('Previous code restored from auto-save');
    }

    // Setup behavior tracking after editor is ready
    if (typeof setupBehaviorTracking === 'function' && sqlEditor) {
        setupBehaviorTracking(sqlEditor);
        console.log('[SQL Challenge] Behavior tracking initialized');
    }

    return true;
}

// Show auto-save notification
function showAutoSaveNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'alert alert-info fade show position-fixed';
    notification.style.cssText = 'top: 70px; right: 20px; z-index: 1050; max-width: 350px; padding: 0.75rem 2.5rem 0.75rem 1rem; position: relative;';
    
    // Create message content
    const messageContent = document.createElement('div');
    messageContent.style.cssText = 'display: flex; align-items: center;';
    messageContent.innerHTML = `<i class="fas fa-save me-2"></i><span>${message}</span>`;
    
    // Create close button
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'btn-close btn-sm';
    closeButton.style.cssText = 'position: absolute; top: 50%; right: 0.5rem; transform: translateY(-50%); padding: 0.25rem; font-size: 0.875rem;';
    closeButton.onclick = function() { notification.remove(); };
    
    notification.appendChild(messageContent);
    notification.appendChild(closeButton);
    document.body.appendChild(notification);
    
    // Auto-hide after 3 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 3000);
}

// Clear saved code when challenge is solved
function clearSavedCode() {
    const challengeId = document.getElementById('challenge-id').value;
    const userId = (CTFd && CTFd.user) ? CTFd.user.id : 'anonymous';
    const storageKey = `sql-challenge-user${userId}-ch${challengeId}-code`;
    localStorage.removeItem(storageKey);
}

// Reset SQL Editor
function resetSQLEditor() {
    // Confirm before resetting
    if (!confirm('Are you sure you want to reset the editor? This will clear all your current code.')) {
        return;
    }
    
    // Clear the editor
    if (sqlEditor) {
        sqlEditor.setValue('');
        sqlEditor.focus();
    } else {
        const textarea = document.getElementById('challenge-input');
        if (textarea) {
            textarea.value = '';
        }
    }
    
    // Clear localStorage
    const challengeId = document.getElementById('challenge-id').value;
    const userId = (CTFd && CTFd.user) ? CTFd.user.id : 'anonymous';
    const storageKey = `sql-challenge-user${userId}-ch${challengeId}-code`;
    localStorage.removeItem(storageKey);
    
    // Clear results
    const container = document.getElementById('query-result-container');
    if (container) {
        container.innerHTML = `
            <div class="text-muted text-center py-5">
                <i class="fas fa-database fa-3x mb-3"></i>
                <p>Execute a query to see results</p>
            </div>
        `;
    }
    
    // Show notification
    showAutoSaveNotification('Editor has been reset');
}

// Execute SQL Query (without submission)
async function executeSQLQuery() {
    const challengeId = document.getElementById('challenge-id').value;
    const submission = sqlEditor ? sqlEditor.getValue() : document.getElementById('challenge-input').value;
    // Get user information from CTFd object
    const userId = (CTFd && CTFd.user) ? CTFd.user.id : null;
    const userName = (CTFd && CTFd.user) ? CTFd.user.name : 'anonymous';
    
    if (!submission.trim()) {
        alert('Please enter a SQL query');
        return;
    }
    
    try {
        const requestBody = {
            challenge_id: parseInt(challengeId),
            submission: submission,
            preview: true,  // Flag to indicate this is just a preview/test
            user_id: userId,
            user_name: userName
        };
        // Request body prepared
        
        const response = await fetch('/api/v1/challenges/attempt', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'CSRF-Token': init.csrfNonce
            },
            body: JSON.stringify(requestBody)
        });
        
        // Response received
        if (!response.ok) {
            console.error('Response not OK:', response.statusText);
        }
        
        // First get the response as text to debug
        const responseText = await response.text();
        // Response text received
        
        // Try to parse as JSON
        let result;
        try {
            result = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response as JSON:', e);
            console.error('Response was:', responseText);
            alert('Server returned invalid JSON response');
            return;
        }
        // Result parsed
        
        // Check if result has the expected structure
        if (!result || typeof result !== 'object') {
            console.error('Invalid result structure:', result);
            alert('Invalid response from server');
            return;
        }
        
        // CTFd API returns {success: bool, data: {...}} structure
        // We need to wrap our result if it doesn't have this structure
        if (!result.hasOwnProperty('data')) {
            // Wrapping result in CTFd format
            const wrappedResult = {
                success: true,
                data: result
            };
            displayResult(wrappedResult, true);
        } else {
            displayResult(result, true);
        }
        
    } catch (error) {
        console.error('Error executing query:', error);
        console.error('Error details:', error.message, error.stack);
        alert('Error executing query. Please check console for details.');
    }
}

// Submit SQL Challenge
async function submitSQLChallenge() {
    const challengeId = document.getElementById('challenge-id').value;
    const submission = sqlEditor ? sqlEditor.getValue() : document.getElementById('challenge-input').value;
    // Get user information from CTFd object
    const userId = (CTFd && CTFd.user) ? CTFd.user.id : null;
    const userName = (CTFd && CTFd.user) ? CTFd.user.name : 'anonymous';

    if (!submission.trim()) {
        alert('Please enter a SQL query');
        return;
    }
    
    // Check deadline before submitting
    const deadlineElement = document.getElementById('deadline-time');
    if (deadlineElement) {
        const deadlineStr = deadlineElement.getAttribute('data-deadline');
        if (deadlineStr) {
            const deadline = new Date(deadlineStr);
            const now = new Date();
            if (now > deadline) {
                // Display deadline error as result instead of alert
                const deadlineResult = {
                    success: true,
                    data: {
                        status: 'incorrect',
                        message: 'Submission deadline has passed'
                    }
                };
                displayResult(deadlineResult, false);
                return;
            }
        }
    }
    
    try {
        const response = await fetch('/api/v1/challenges/attempt', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'CSRF-Token': init.csrfNonce
            },
            body: JSON.stringify({
                challenge_id: parseInt(challengeId),
                submission: submission,
                user_id: userId,
                user_name: userName
            })
        });
        
        const result = await response.json();
        // Submit result received
        
        // Check if result has the expected structure
        if (!result || typeof result !== 'object') {
            console.error('Invalid result structure:', result);
            alert('Invalid response from server');
            return;
        }

        if (behaviorLogger) {
            const submitStatus = result.data.status || 'unknown';
            behaviorLogger.logEvent('submit', {
                query_text: submission,
                query_length: submission.length,
                submit_status: submitStatus
            })
        }
        
        // CTFd API returns {success: bool, data: {...}} structure
        if (!result.hasOwnProperty('data')) {
            // Wrapping result in CTFd format
            const wrappedResult = {
                success: true,
                data: result
            };
            displayResult(wrappedResult, false);
        } else {
            displayResult(result, false);
        }
        
    } catch (error) {
        console.error('Error submitting challenge:', error);
        alert('Error submitting challenge. Please try again.');
    }
}

// Display Result
function displayResult(result, isPreview = false) {
    const container = document.getElementById('query-result-container');
    
    // Clear and prepare container
    container.innerHTML = '';
    
    // Parse message first to check if it's a preview
    let message = result.data.message || '';
    const isActuallyPreview = message.startsWith('[PREVIEW]');
    
    // Create status message
    const statusDiv = document.createElement('div');
    const isAlreadySolved = result.data.status === 'already_solved';
    statusDiv.className = result.data.status === 'correct' || isAlreadySolved ? 'alert alert-success' : 
                          (result.data.status === 'incorrect' && !isActuallyPreview) ? 'alert alert-danger' : 
                          isActuallyPreview ? 'alert alert-info' :
                          'alert alert-warning';
    statusDiv.innerHTML = '<span id="status-text"></span>';
    
    // Continue processing message
    if (isActuallyPreview) {
        message = message.replace('[PREVIEW]\n', '');
    }
    
    // Remove "but you already solved this" from message for parsing
    if (isAlreadySolved) {
        message = message.replace(' but you already solved this', '');
    }
    
    // Processing message and status
    
    const lines = message.split('\n');
    let statusTextContent = '';
    let userResult = null;
    let expectedResult = null;
    let isUserResult = false;
    let isExpectedResult = false;
    let tempContent = [];
    
    for (const line of lines) {
        if (line === '[USER_RESULT]') {
            isUserResult = true;
            tempContent = [];
        } else if (line === '[/USER_RESULT]') {
            isUserResult = false;
            try {
                const jsonStr = tempContent.join('');
                // Parsing user result JSON
                userResult = JSON.parse(jsonStr);
                // Parsed user result
            } catch(e) {
                console.error('Failed to parse user result:', e, 'JSON string:', tempContent.join(''));
            }
        } else if (line === '[EXPECTED_RESULT]') {
            isExpectedResult = true;
            tempContent = [];
        } else if (line === '[/EXPECTED_RESULT]') {
            isExpectedResult = false;
            try {
                const jsonStr = tempContent.join('');
                // Parsing expected result JSON
                expectedResult = JSON.parse(jsonStr);
                // Parsed expected result
            } catch(e) {
                console.error('Failed to parse expected result:', e, 'JSON string:', tempContent.join(''));
            }
        } else if (isUserResult || isExpectedResult) {
            tempContent.push(line);
        } else {
            statusTextContent += line + '\n';
        }
    }
    
    container.appendChild(statusDiv);
    let finalStatusText = statusTextContent.trim();
    if (isAlreadySolved) {
        finalStatusText += ' (Already solved)';
    }
    document.getElementById('status-text').innerHTML = finalStatusText;
    
    // Render user result
    if (userResult) {
        // Rendering user result table
        const userCard = document.createElement('div');
        userCard.className = 'card mb-2';
        const tableHtml = renderTable(userResult);
        // Generated table HTML
        
        // Create card structure manually to avoid template literal issues
        const cardHeader = document.createElement('div');
        cardHeader.className = 'card-header bg-primary text-white';
        cardHeader.innerHTML = '<h6 class="mb-0"><i class="fas fa-code"></i> Your Query Result</h6>';
        
        const cardBody = document.createElement('div');
        cardBody.className = 'card-body p-0';
        
        const tableContainer = document.createElement('div');
        tableContainer.className = 'table-responsive';
        tableContainer.innerHTML = tableHtml;
        
        cardBody.appendChild(tableContainer);
        userCard.appendChild(cardHeader);
        userCard.appendChild(cardBody);
        container.appendChild(userCard);
    } else {
        // No user result to render
    }
    
    // Show success modal if correct (only for actual submissions, not previews)
    if (result.data.status === 'correct' && !isPreview) {
        // Challenge solved! Showing success modal
        
        // Clear saved code since challenge is solved
        clearSavedCode();
        
        // Update earned points if available
        if (result.data.points) {
            document.getElementById('earned-points').textContent = result.data.points;
        }
        
        // Show modal after a short delay to let the result display first
        setTimeout(() => {
            try {
                const modalElement = document.getElementById('successModal');
                // Modal element found
                
                if (modalElement) {
                    // Manually show modal
                    modalElement.classList.add('show');
                    modalElement.style.display = 'block';
                    modalElement.setAttribute('aria-hidden', 'false');
                    document.body.classList.add('modal-open');
                    // Modal shown manually
                } else {
                    console.error('Modal element not found!'); // Debug log
                }
            } catch (error) {
                console.error('Error showing modal:', error); // Debug log
            }
        }, 1000);
    }
    

}

// Render Table
function renderTable(data) {
    // Rendering table
    
    if (!data || !data.columns || !data.rows) {
        // Invalid data structure for table
        return '<p class="p-3 text-muted">No data to display</p>';
    }
    
    if (data.rows.length === 0) {
        // Empty rows array
        return '<p class="p-3 text-muted">Empty result set</p>';
    }
    
    let html = '<table class="table table-sm table-striped mb-0">';
    
    // Header
    html += '<thead class="table-dark"><tr>';
    for (const col of data.columns) {
        html += `<th>${escapeHtml(col)}</th>`;
    }
    html += '</tr></thead>';
    
    // Body
    html += '<tbody>';
    for (const row of data.rows) {
        html += '<tr>';
        for (const cell of row) {
            html += `<td>${escapeHtml(cell)}</td>`;
        }
        html += '</tr>';
    }
    html += '</tbody>';
    
    html += '</table>';
    html += `<div class="row-count-footer p-2 text-muted small">${data.row_count} row(s) returned</div>`;
    
    return html;
}

// Escape HTML
function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Panel Resize Functionality
function initPanelResize() {
    const resizeHandle = document.getElementById('resize-handle');
    const leftPanel = document.getElementById('left-panel');
    const rightPanel = document.getElementById('right-panel');
    const container = document.getElementById('resize-container');
    
    let isResizing = false;
    let startX = 0;
    let startLeftWidth = 0;
    
    resizeHandle.addEventListener('mousedown', function(e) {
        isResizing = true;
        startX = e.clientX;
        startLeftWidth = leftPanel.offsetWidth;
        
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        
        e.preventDefault();
    });
    
    document.addEventListener('mousemove', function(e) {
        if (!isResizing) return;
        
        const containerWidth = container.offsetWidth;
        const newLeftWidth = startLeftWidth + (e.clientX - startX);
        const leftWidthPercent = (newLeftWidth / containerWidth) * 100;
        
        // Limit resize between 20% and 70%
        if (leftWidthPercent >= 20 && leftWidthPercent <= 70) {
            leftPanel.style.width = leftWidthPercent + '%';
            rightPanel.style.width = (100 - leftWidthPercent) + '%';
            
            // Trigger CodeMirror refresh after resize
            if (sqlEditor) {
                setTimeout(() => {
                    sqlEditor.refresh();
                    // Keep focus if it was focused before
                    if (document.activeElement && document.activeElement.classList.contains('CodeMirror')) {
                        sqlEditor.focus();
                    }
                }, 10);
            }
        }
    });
    
    document.addEventListener('mouseup', function() {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            
            // Save panel width to localStorage
            const leftWidth = leftPanel.style.width;
            if (leftWidth) {
                localStorage.setItem('sql-challenge-left-width', leftWidth);
            }
        }
    });
    
    // Restore saved panel width
    const savedWidth = localStorage.getItem('sql-challenge-left-width');
    if (savedWidth) {
        leftPanel.style.width = savedWidth;
        rightPanel.style.width = (100 - parseFloat(savedWidth)) + '%';
    }
}

// Vertical Panel Resize Functionality
function initVerticalResize() {
    const resizeHandle = document.getElementById('vertical-resize-handle');
    const editorSection = document.getElementById('editor-section');
    const resultSection = document.getElementById('result-section');
    const container = document.querySelector('.sql-editor-section');
    
    if (!resizeHandle || !editorSection || !resultSection) return;
    
    let isResizing = false;
    let startY = 0;
    let startEditorHeight = 0;
    
    resizeHandle.addEventListener('mousedown', function(e) {
        isResizing = true;
        startY = e.clientY;
        startEditorHeight = editorSection.offsetHeight;
        
        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';
        
        e.preventDefault();
    });
    
    document.addEventListener('mousemove', function(e) {
        if (!isResizing) return;
        
        const containerHeight = container.offsetHeight;
        const newEditorHeight = startEditorHeight + (e.clientY - startY);
        const editorHeightPercent = (newEditorHeight / containerHeight) * 100;
        
        // Limit resize between 20% and 80%
        if (editorHeightPercent >= 20 && editorHeightPercent <= 80) {
            editorSection.style.height = editorHeightPercent + '%';
            resultSection.style.height = (100 - editorHeightPercent - 2) + '%'; // 2% for handle
            
            // Trigger CodeMirror refresh after resize
            if (sqlEditor) {
                setTimeout(() => {
                    sqlEditor.refresh();
                    // Keep focus if it was focused before
                    if (document.activeElement && document.activeElement.classList.contains('CodeMirror')) {
                        sqlEditor.focus();
                    }
                }, 10);
            }
        }
    });
    
    document.addEventListener('mouseup', function() {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            
            // Save editor height to localStorage
            const editorHeight = editorSection.style.height;
            if (editorHeight) {
                localStorage.setItem('sql-challenge-editor-height', editorHeight);
            }
        }
    });
    
    // Restore saved editor height
    const savedHeight = localStorage.getItem('sql-challenge-editor-height');
    if (savedHeight) {
        editorSection.style.height = savedHeight;
        resultSection.style.height = (100 - parseFloat(savedHeight) - 2) + '%';
    }
}

// Update Deadline Display
function updateDeadlineDisplay() {
    const deadlineElement = document.getElementById('deadline-time');
    if (!deadlineElement) return;
    
    const deadlineStr = deadlineElement.getAttribute('data-deadline');
    if (!deadlineStr) return;
    
    const deadline = new Date(deadlineStr);
    const now = new Date();
    const diff = deadline - now;
    
    if (diff <= 0) {
        deadlineElement.textContent = 'Expired';
        deadlineElement.closest('.deadline-display').classList.add('deadline-danger');
        return;
    }
    
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);
    
    let timeStr = '';
    if (days > 0) {
        timeStr = `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        timeStr = `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
        timeStr = `${minutes}m ${seconds}s`;
    } else {
        timeStr = `${seconds}s`;
    }
    
    deadlineElement.textContent = timeStr + ' remaining';
    
    // Add warning colors based on time remaining
    const deadlineDisplay = deadlineElement.closest('.deadline-display');
    deadlineDisplay.classList.remove('deadline-warning', 'deadline-danger');
    
    if (days === 0 && hours < 1) {
        deadlineDisplay.classList.add('deadline-danger');
    } else if (days === 0 && hours < 6) {
        deadlineDisplay.classList.add('deadline-warning');
    }
}

// Debug localStorage
function debugLocalStorage() {
    console.log('=== LocalStorage Debug ===');
    console.log('All localStorage keys:', Object.keys(localStorage));
    console.log('SQL related keys:');
    for (let key in localStorage) {
        if (key.includes('sql-challenge')) {
            console.log(`  ${key}: ${localStorage[key].substring(0, 50)}...`);
        }
    }
    console.log('========================');
}

// Manual save/load functions for testing
window.testSaveCode = function(code) {
    const challengeId = document.getElementById('challenge-id').value;
    const userId = (CTFd && CTFd.user) ? CTFd.user.id : 'test';
    const storageKey = `sql-challenge-user${userId}-ch${challengeId}-code`;
    localStorage.setItem(storageKey, code || 'SELECT * FROM test;');
    console.log(`Saved to ${storageKey}`);
    debugLocalStorage();
};

window.testLoadCode = function() {
    const challengeId = document.getElementById('challenge-id').value;
    const userId = (CTFd && CTFd.user) ? CTFd.user.id : 'test';
    const storageKey = `sql-challenge-user${userId}-ch${challengeId}-code`;
    const code = localStorage.getItem(storageKey);
    console.log(`Loading from ${storageKey}:`, code);
    if (code && sqlEditor) {
        sqlEditor.setValue(code);
        console.log('Code loaded into editor');
    }
    return code;
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Try multiple initialization strategies
    initSQLEditor();
    
    // Also try after a delay in case CTFd loads later
    setTimeout(() => {
        if (!sqlEditor) {
            initSQLEditor();
        }
    }, 500);
    
    setTimeout(() => {
        if (!sqlEditor) {
            initSQLEditor();
        }
    }, 1000);
    
    initPanelResize();
    initVerticalResize();
    
    // Update deadline display
    updateDeadlineDisplay();
    setInterval(updateDeadlineDisplay, 1000);
    
    // Add button event listeners
    const resetBtn = document.getElementById('challenge-reset');
    const executeBtn = document.getElementById('challenge-execute');
    const submitBtn = document.getElementById('challenge-submit');

    if (resetBtn) resetBtn.addEventListener('click', resetSQLEditor);
    if (executeBtn) executeBtn.addEventListener('click', executeSQLQuery);
    if (submitBtn) submitBtn.addEventListener('click', submitSQLChallenge);

    // Add modal close functionality
    const modalCloseButtons = document.querySelectorAll('[data-bs-dismiss="modal"]');
    modalCloseButtons.forEach(button => {
        button.addEventListener('click', function() {
            const modal = this.closest('.modal');
            if (modal) {
                modal.classList.remove('show');
                modal.style.display = 'none';
                modal.setAttribute('aria-hidden', 'true');
                document.body.classList.remove('modal-open');
            }
        });
    });
});

// Also try on window load
window.addEventListener('load', function() {
    if (!sqlEditor) {
        initSQLEditor();
    }
});