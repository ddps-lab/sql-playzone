CTFd.plugin.run((_CTFd) => {
    const $ = _CTFd.lib.$;
    
    // Submit button handler for SQL challenge creation
    $('#submit').click(function(e) {
        e.preventDefault();
        
        // Get form data
        const form = $(this).closest('form');
        const data = form.serializeJSON();
        
        // Create challenge via API
        CTFd.fetch('/api/v1/challenges', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                // Redirect directly to challenge edit page, skipping the options modal
                const challenge_id = result.data.id;
                window.location = CTFd.config.urlRoot + '/admin/challenges/' + challenge_id;
            } else {
                // Show error message
                if (result.errors) {
                    Object.keys(result.errors).forEach(key => {
                        const error = result.errors[key];
                        const field = form.find(`[name="${key}"]`);
                        field.addClass('is-invalid');
                        field.after(`<div class="invalid-feedback">${error}</div>`);
                    });
                } else {
                    alert('Error creating challenge');
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error creating challenge: ' + error.message);
        });
    });
    
    // Test SQL queries button handler
    $('#test-sql-btn').click(function() {
        const initQuery = $('textarea[name="init_query"]').val();
        const solutionQuery = $('textarea[name="solution_query"]').val();
        
        if (!solutionQuery) {
            alert('Please enter a solution query to test');
            return;
        }
        
        // Show loading state
        $('#test-results').show();
        $('#test-output').html('<div class="spinner-border spinner-border-sm" role="status"><span class="sr-only">Testing...</span></div> Testing queries...');
        
        // Test the queries via API
        CTFd.fetch('/api/v1/challenges/test-sql', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                init_query: initQuery,
                test_query: solutionQuery
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Display results in a table
                let html = '<div class="alert alert-success">Query executed successfully!</div>';
                
                if (data.rows && data.rows.length > 0) {
                    html += '<table class="table table-sm table-bordered">';
                    
                    // Add headers
                    if (data.columns && data.columns.length > 0) {
                        html += '<thead><tr>';
                        data.columns.forEach(col => {
                            html += `<th>${col}</th>`;
                        });
                        html += '</tr></thead>';
                    }
                    
                    // Add rows
                    html += '<tbody>';
                    data.rows.forEach(row => {
                        html += '<tr>';
                        row.forEach(cell => {
                            html += `<td>${cell}</td>`;
                        });
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                } else {
                    html += '<p>Query executed but returned no results.</p>';
                }
                
                $('#test-output').html(html);
            } else {
                $('#test-output').html(`<div class="alert alert-danger">Error: ${data.error}</div>`);
            }
        })
        .catch(error => {
            $('#test-output').html(`<div class="alert alert-danger">Failed to test queries: ${error}</div>`);
        });
    });
});