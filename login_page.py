"""
Login page HTML template for the Owlet Dream Logger.
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Owlet Dream Logger - Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .login-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 50px 40px;
            width: 100%;
            max-width: 420px;
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo h1 {
            font-size: 2rem;
            font-weight: 800;
            color: #1f2937;
            margin-bottom: 8px;
        }
        
        .logo p {
            color: #6b7280;
            font-size: 0.95rem;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            font-weight: 600;
            color: #374151;
            margin-bottom: 8px;
            font-size: 0.9rem;
        }
        
        input[type="email"],
        input[type="password"],
        select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 10px;
            font-size: 1rem;
            font-family: 'Inter', sans-serif;
            transition: all 0.2s;
            background: #f9fafb;
        }
        
        input[type="email"]:focus,
        input[type="password"]:focus,
        select:focus {
            outline: none;
            border-color: #667eea;
            background: white;
        }
        
        select {
            cursor: pointer;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23374151' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 16px center;
            padding-right: 40px;
        }
        
        .btn-login {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-top: 10px;
        }
        
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        .btn-login:active {
            transform: translateY(0);
        }
        
        .error-message {
            background: #fee2e2;
            color: #991b1b;
            padding: 12px 16px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-size: 0.9rem;
            display: none;
            border-left: 4px solid #ef4444;
        }
        
        .error-message.show {
            display: block;
        }
        
        .info-text {
            text-align: center;
            color: #6b7280;
            font-size: 0.85rem;
            margin-top: 20px;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <h1>🦉 Owlet Logger</h1>
            <p>Real-time Baby Monitor Dashboard</p>
        </div>
        
        <div id="error" class="error-message"></div>
        
        <form id="loginForm" onsubmit="return false;">
            <div class="form-group">
                <label for="email">Email Address</label>
                <input 
                    type="email" 
                    id="email" 
                    name="email" 
                    placeholder="your.email@example.com" 
                    required
                    autocomplete="email"
                >
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input 
                    type="password" 
                    id="password" 
                    name="password" 
                    placeholder="Enter your password" 
                    required
                    autocomplete="current-password"
                >
            </div>
            
            <div class="form-group">
                <label for="region">Region</label>
                <select id="region" name="region" required>
                    <option value="world" selected>World</option>
                    <option value="europe">Europe</option>
                </select>
            </div>
            
            <button type="submit" class="btn-login">Connect to Dashboard</button>
        </form>
        
        <p class="info-text">
            Enter your Owlet account credentials to access the real-time monitoring dashboard.
        </p>
    </div>
    
    <script>
        const form = document.getElementById('loginForm');
        const errorDiv = document.getElementById('error');
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            
            console.log('Form submitted, preventing default...');
            
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const region = document.getElementById('region').value;
            
            console.log('Login attempt:', { email, region });
            
            // Hide previous errors
            errorDiv.classList.remove('show');
            
            // Send login credentials to server
            try {
                console.log('Sending fetch request to /login...');
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',  // Important: Include cookies in request
                    body: JSON.stringify({ email, password, region })
                });
                
                console.log('Response status:', response.status);
                const data = await response.json();
                console.log('Response data:', data);
                
                if (response.ok && data.success) {
                    console.log('Login successful, redirecting...');
                    // Redirect to dashboard with session
                    window.location.href = '/dashboard';
                } else {
                    // Show error message
                    console.error('Login failed:', data);
                    errorDiv.textContent = data.error || 'Login failed. Please check your credentials.';
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                console.error('Connection error:', error);
                errorDiv.textContent = 'Connection error: ' + error.message;
                errorDiv.classList.add('show');
            }
            
            return false;
        });
        
        console.log('Login page script loaded successfully');
    </script>
</body>
</html>
"""
