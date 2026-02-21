document.addEventListener('DOMContentLoaded', () => {
    // Initialize CodeMirror
    const editor = CodeMirror.fromTextArea(document.getElementById('code-editor'), {
        mode: 'text/x-c++src', // Assuming C++ based on the provided example
        theme: 'dracula',
        lineNumbers: true,
        autoCloseBrackets: true,
        indentUnit: 4
    });

    const runBtn = document.getElementById('run-btn');
    const inputArea = document.getElementById('input-area');
    const outputArea = document.getElementById('output-area');

    runBtn.addEventListener('click', async () => {
        const code = editor.getValue();
        const input = inputArea.value;

        outputArea.textContent = 'Running...';
        outputArea.classList.remove('error');

        try {
            const response = await fetch('/api/run', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    sourceCode: code,
                    input: input
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.error) {
                outputArea.textContent = `Compilation Error:\n${result.error}`;
                outputArea.classList.add('error');
            } else if (result.results) {
                // The API structure is data -> results -> exitCode
                const data = result.results;
                const exitCode = data.results ? data.results.exitCode : 0;

                // Just show the output content (stdout + stderr if any)
                let output = data.stdout || "";
                if (data.stderr) {
                    output += "\n" + data.stderr;
                }
                if (!output) {
                    output = "No output";
                }
                outputArea.textContent = output;

                // Keep error class if exit code is bad, just for styling (red text)
                if (exitCode !== 0) {
                    outputArea.classList.add('error');
                } else {
                    outputArea.classList.remove('error');
                }
            } else {
                outputArea.textContent = JSON.stringify(result, null, 2);
            }

        } catch (error) {
            outputArea.textContent = `Error: ${error.message}`;
            outputArea.classList.add('error');
        }
    });

    const submitBtn = document.getElementById('submit-btn');
    submitBtn.addEventListener('click', async () => {
        const code = editor.getValue();
        outputArea.textContent = 'Submitting...';
        outputArea.classList.remove('error');

        try {
            const response = await fetch('/api/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sourceCode: code })
            });

            if (!response.ok) throw new Error(`Server error: ${response.statusText}`);

            const result = await response.json();

            if (result.results) {
                // Display just the score as requested
                const score = result.results.score !== undefined ? result.results.score : 'N/A';
                outputArea.textContent = `Score: ${score}`;

                // Optional: Add color based on score
                if (score == 100) outputArea.classList.remove('error');
                else outputArea.classList.add('error');
            } else {
                outputArea.textContent = `Submission Received.\nJob ID: ${result.evalJobId || result.message}\n(Check server logs for details if not finished)`;
            }
        } catch (error) {
            outputArea.textContent = `Error: ${error.message}`;
            outputArea.classList.add('error');
        }
    });
});
