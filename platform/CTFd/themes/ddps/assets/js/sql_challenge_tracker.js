/**
 * SQL Challenge Behavior Tracking System
 * Tracks user interactions with the SQL editor for AI usage analysis
 */

class BehaviorLogger {
    constructor() {
        this.sessionId = this.generateUUID();

        // Get challenge and user info
        const solvedBadge = document.querySelector('.badge.bg-success');
        const badgeText = solvedBadge ? solvedBadge.textContent.trim() : null;
        console.log('[BehaviorLogger] Badge check:', {
            badge: solvedBadge,
            text: badgeText,
            isSolved: badgeText === 'Solved'
        });

        this.baseInfo = {
            session_id: this.sessionId,
            user_id: (CTFd && CTFd.user) ? CTFd.user.id : -1,
            user_name: (CTFd && CTFd.user) ? CTFd.user.name : 'anonymous',
            challenge_id: parseInt(document.getElementById('challenge-id').value),
            challenge_name: document.querySelector('.challenge-name')?.textContent || '',
            already_solved: badgeText === 'Solved'
        };

        this.eventBuffer = [];
        this.flushInterval = setInterval(() => this.flush(), 5000); // Flush every 5 seconds

        console.log('[BehaviorLogger] Initialized with session:', this.sessionId);
    }

    /**
     * Create a standardized event object
     */
    createEvent(eventType, data = {}) {
        return {
            timestamp: new Date().toISOString(),
            ...this.baseInfo,
            event_type: eventType,
            typed_text: data.typed_text || "",
            typed_length: data.typed_length || 0,
            pasted_text: data.pasted_text || "",
            pasted_length: data.pasted_length || 0,
            query_text: data.query_text || "",
            query_length: data.query_length || 0,
            submit_status: data.submit_status || "",
        };
    }

    /**
     * Log an event
     */
    logEvent(eventType, data = {}) {
        const event = this.createEvent(eventType, data);
        this.eventBuffer.push(event);

        // console.log(`[BehaviorLogger] Event logged: ${eventType}`, data);

        // Flush if buffer is large
        if (this.eventBuffer.length >= 20) {
            this.flush();
        }
    }

    /**
     * Send buffered events to server
     */
    async flush() {
        if (this.eventBuffer.length === 0) return;

        const events = this.eventBuffer.splice(0); // Get all events and clear buffer

        try {
            // Debug CSRF token
            const csrfToken = (typeof init !== 'undefined' && init.csrfNonce) ? init.csrfNonce : '';

            const response = await fetch('/api/v1/challenges/behavior', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'CSRF-Token': csrfToken
                },
                body: JSON.stringify({ events })
            });

            if (response.ok) {
                // console.log(`[BehaviorLogger] Flushed ${events.length} events`);
            } else {
                console.error('[BehaviorLogger] Failed to flush events:', response.status, response.errors);
                // Put events back if failed
                this.eventBuffer.unshift(...events);
            }
        } catch (error) {
            console.error('[BehaviorLogger] Error flushing events:', error);
            // Put events back if failed
            this.eventBuffer.unshift(...events);
        }
    }

    /**
     * Clean up and flush remaining events
     */
    destroy() {
        console.log('[BehaviorLogger] Destroying logger');
        clearInterval(this.flushInterval);
        this.flush(); // Final flush
    }

    /**
     * Generate a UUID v4
     */
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
}

// Global logger instance
let behaviorLogger = null;

/**
 * Initialize behavior tracking for the SQL editor
 */
function setupBehaviorTracking(sqlEditor) {
    // Clean up existing logger
    if (behaviorLogger) {
        behaviorLogger.destroy();
    }

    // Create new logger
    window.behaviorLogger = behaviorLogger = new BehaviorLogger();

    // Track word completion with delimiters
    let wordBuffer = '';

    sqlEditor.on('inputRead', function(cm, event) {
        if (event.origin === '+input' && event.text && event.text[0]) {
            const inputChar = event.text[0];
            const currentQuery = cm.getValue();

            // Add character to buffer (including delimiters)
            wordBuffer += inputChar;

            // Check if it's a delimiter (space, semicolon, enter)
            if (inputChar === ' ' || inputChar === ';' || inputChar === '\n') {
                // Log the complete word with delimiter
                if (wordBuffer.length > 0) {
                    behaviorLogger.logEvent('word_typed', {
                        typed_text: wordBuffer,  // Includes the delimiter
                        typed_length: wordBuffer.length,
                        query_text: currentQuery,
                        query_length: currentQuery.length
                    });
                }
                wordBuffer = '';  // Reset buffer
            }
        }
    });

    // Track paste events
    sqlEditor.on('change', function(cm, change) {
        const currentQuery = cm.getValue();

        // Paste event only
        if (change.origin === 'paste') {
            const pastedText = change.text.join('\n');
            behaviorLogger.logEvent('paste', {
                pasted_text: pastedText,
                pasted_length: pastedText.length,
                query_text: currentQuery,
                query_length: currentQuery.length
            });
        }
    });

    // Track focus/blur
    sqlEditor.on('focus', function() {
        const query = sqlEditor.getValue();
        behaviorLogger.logEvent('focus', {
            query_length: query.length,
            query_text: query
        });
    });

    sqlEditor.on('blur', function() {
        const query = sqlEditor.getValue();
        behaviorLogger.logEvent('blur', {
            query_length: query.length,
            query_text: query
        });
    });

    // Track tab visibility changes
    document.addEventListener('visibilitychange', function() {
        const query = sqlEditor ? sqlEditor.getValue() : '';
        if (document.hidden) {
            behaviorLogger.logEvent('tab_hide', {
                query_length: query.length,
                query_text: query
            });
        } else {
            behaviorLogger.logEvent('tab_show', {
                query_length: query.length,
                query_text: query
            });
        }
    });

    // Track execute button
    // Currently Useless as execute does not run the query
    // const executeBtn = document.getElementById('challenge-execute');
    // if (executeBtn) {
    //     executeBtn.addEventListener('click', function() {
    //         const query = sqlEditor.getValue();
    //         behaviorLogger.logEvent('execute', {
    //             query_length: query.length,
    //             query_text: query
    //         });
    //     });
    // }

    // Track submit button
    // This will be processed by submitSQLChallenge function in sql_challenges.js
    // const submitBtn = document.getElementById('challenge-submit');
    // if (submitBtn) {
    //     submitBtn.addEventListener('click', function() {
    //         const query = sqlEditor.getValue();
    //         behaviorLogger.logEvent('submit', {
    //             query_length: query.length,
    //             query_text: query
    //         });
    //     });
    // }

    // Track reset button
    const resetBtn = document.getElementById('challenge-reset');
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            behaviorLogger.logEvent('reset', {
                query_length: sqlEditor ? sqlEditor.getValue().length : 0
            });
        });
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
        if (behaviorLogger) {
            behaviorLogger.destroy();
        }
    });

    console.log('[BehaviorTracking] Setup complete');
}

// Export for use in other scripts
window.BehaviorLogger = BehaviorLogger;
window.setupBehaviorTracking = setupBehaviorTracking;
window.behaviorLogger = behaviorLogger;