let editor;
let currentProblem = null;
let problems = [];

document.addEventListener('DOMContentLoaded', async () => {
    // Initialize CodeMirror
    editor = CodeMirror.fromTextArea(document.getElementById('code-editor'), {
        mode: 'text/x-c++src',
        theme: 'dracula',
        lineNumbers: true,
        autoCloseBrackets: true,
        indentUnit: 4
    });

    // Load problems from server
    await loadProblems();

    // Set up event listeners
    const problemSelect = document.getElementById('problem-select');
    const runBtn = document.getElementById('run-btn');
    const submitBtn = document.getElementById('submit-btn');
    const inputArea = document.getElementById('input-area');
    const outputArea = document.getElementById('output-area');

    problemSelect.addEventListener('change', (e) => {
        const problemId = e.target.value;
        if (problemId) {
            loadProblem(problemId);
        }
    });

    runBtn.addEventListener('click', async () => {
        if (!currentProblem) {
            outputArea.textContent = 'Please select a problem first';
            outputArea.classList.add('error');
            return;
        }

        const code = editor.getValue();
        const input = inputArea.value;

        outputArea.textContent = 'Running...';
        outputArea.classList.remove('error');

        try {
            const response = await fetch(`/api/run/${currentProblem.id}`, {
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
                const data = result.results;
                const exitCode = data.results ? data.results.exitCode : 0;

                let output = data.stdout || "";
                if (data.stderr) {
                    output += "\n" + data.stderr;
                }
                if (!output) {
                    output = "No output";
                }
                outputArea.textContent = output;

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

    submitBtn.addEventListener('click', async () => {
        if (!currentProblem) {
            outputArea.textContent = 'Please select a problem first';
            outputArea.classList.add('error');
            return;
        }

        const code = editor.getValue();
        outputArea.textContent = 'Submitting...';
        outputArea.classList.remove('error');

        try {
            const response = await fetch(`/api/submit/${currentProblem.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sourceCode: code })
            });

            if (!response.ok) throw new Error(`Server error: ${response.statusText}`);

            const result = await response.json();

            console.log('Submission result:', result);

            if (result.results) {
                const score = result.results.score !== undefined ? result.results.score : 'N/A';
                outputArea.textContent = `Score: ${score}`;

                if (score == 100) {
                    outputArea.classList.remove('error');
                } else {
                    outputArea.classList.add('error');
                }
            } else {
                outputArea.textContent = `Submission Received.\nJob ID: ${result.evalJobId || result.message}\n(Check server logs for details if not finished)`;
            }
        } catch (error) {
            outputArea.textContent = `Error: ${error.message}`;
            outputArea.classList.add('error');
        }
    });
});

async function loadProblems() {
    try {
        const response = await fetch('/api/problems');
        if (!response.ok) {
            throw new Error('Failed to load problems');
        }

        const data = await response.json();
        problems = data.problems;

        const problemSelect = document.getElementById('problem-select');
        problemSelect.innerHTML = '<option value="">-- Select a Problem --</option>';

        problems.forEach(problem => {
            const option = document.createElement('option');
            option.value = problem.id;
            option.textContent = problem.name;
            problemSelect.appendChild(option);
        });

        // Auto-select first problem
        if (problems.length > 0) {
            problemSelect.value = problems[0].id;
            loadProblem(problems[0].id);
        }

    } catch (error) {
        console.error('Error loading problems:', error);
        document.getElementById('problem-description').textContent =
            'Error loading problems. Please check the server connection.';
    }
}

function loadProblem(problemId) {
    const problem = problems.find(p => p.id === problemId);
    if (!problem) return;

    currentProblem = problem;

    // Update problem description
    document.getElementById('problem-description').textContent = problem.description;

    // Update sample I/O
    document.getElementById('sample-input').textContent = problem.sampleInput;
    document.getElementById('sample-output').textContent = problem.sampleOutput;

    // Update code editor with starter code
    editor.setValue(problem.starterCode);

    // Update input area with sample input
    document.getElementById('input-area').value = problem.sampleInput;

    // Clear output
    document.getElementById('output-area').textContent = '';
    document.getElementById('output-area').classList.remove('error');
}
