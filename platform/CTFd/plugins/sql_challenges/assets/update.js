CTFd.plugin.run((_CTFd) => {
    const $ = _CTFd.lib.$;
    
    // Test SQL queries button handler
    $('#test-sql-btn').click(function() {
        const initQuery = $('.challenge-init-query').val();
        const solutionQuery = $('.challenge-solution-query').val();
        
        if (!solutionQuery) {
            alert('Please enter a solution query to test');
            return;
        }
        
        testQuery(initQuery, solutionQuery);
    });
    
    // Toggle custom query section
    $('#test-custom-btn').click(function() {
        $('#custom-query-section').toggle();
    });
    
    // Run custom query
    $('#run-custom-query').click(function() {
        const initQuery = $('.challenge-init-query').val();
        const customQuery = $('#custom-query').val();
        
        if (!customQuery) {
            alert('Please enter a query to test');
            return;
        }
        
        testQuery(initQuery, customQuery);
    });
    
    function testQuery(initQuery, testQuery) {
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
                test_query: testQuery
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
                            html += `<td>${cell !== null ? cell : 'NULL'}</td>`;
                        });
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                    
                    html += `<small class="text-muted">Returned ${data.rows.length} row(s)</small>`;
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
    }
});