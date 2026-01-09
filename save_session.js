/**
 * SeaArt Session Saver
 * 
 * This script connects to a running Chromium-based browser (Chrome, Brave, Edge)
 * via Chrome DevTools Protocol and saves all cookies to seaart_session.json.
 * 
 * WHY NODE.JS?
 * -----------
 * If you're running from WSL (Windows Subsystem for Linux), Python/Playwright
 * cannot connect to Windows browser's localhost due to WSL2 networking isolation.
 * Node.js running on Windows CAN connect, so we use this script instead.
 * 
 * PREREQUISITES:
 * 1. Node.js installed on Windows
 * 2. ws package: npm install ws
 * 
 * USAGE:
 * 1. Close ALL browser windows completely
 * 2. Start browser with remote debugging (from Windows CMD/PowerShell):
 *    
 *    For Brave:
 *    "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" --remote-debugging-port=9224 https://www.seaart.ai
 *    
 *    For Chrome:
 *    "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9224 https://www.seaart.ai
 *    
 *    For Edge:
 *    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9224 https://www.seaart.ai
 * 
 * 3. Login to SeaArt.ai in the browser (if not already logged in)
 * 
 * 4. Run this script (from Windows):
 *    node save_session.js
 * 
 *    Or from WSL (uses Windows Node):
 *    /mnt/c/Windows/System32/cmd.exe /c "cd C:\path\to\project && node save_session.js"
 * 
 * OUTPUT:
 * - seaart_session.json (Playwright-compatible session format)
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const DEBUG_PORT = 9224;
const OUTPUT_FILE = path.join(__dirname, 'seaart_session.json');

async function getWebSocketUrl() {
    return new Promise((resolve, reject) => {
        http.get(`http://127.0.0.1:${DEBUG_PORT}/json/version`, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    resolve(json.webSocketDebuggerUrl);
                } catch (e) {
                    reject(new Error('Failed to parse browser info'));
                }
            });
        }).on('error', (e) => {
            reject(new Error(`Cannot connect to browser on port ${DEBUG_PORT}. ` +
                'Make sure browser is running with --remote-debugging-port=9224'));
        });
    });
}

async function getAllCookies(wsUrl) {
    const WebSocket = require('ws');
    
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        
        ws.on('error', (err) => {
            reject(new Error(`WebSocket error: ${err.message}`));
        });
        
        ws.on('open', () => {
            // Request all cookies via Chrome DevTools Protocol
            ws.send(JSON.stringify({
                id: 1,
                method: 'Storage.getCookies'
            }));
        });
        
        ws.on('message', (data) => {
            const msg = JSON.parse(data);
            if (msg.id === 1) {
                ws.close();
                if (msg.error) {
                    reject(new Error(msg.error.message));
                } else {
                    resolve(msg.result.cookies);
                }
            }
        });
        
        // Timeout after 10 seconds
        setTimeout(() => {
            ws.close();
            reject(new Error('Timeout waiting for cookies'));
        }, 10000);
    });
}

function formatForPlaywright(cookies) {
    // Convert CDP cookie format to Playwright storage_state format
    return {
        cookies: cookies.map(c => ({
            name: c.name,
            value: c.value,
            domain: c.domain,
            path: c.path || '/',
            expires: c.expires || -1,
            httpOnly: c.httpOnly || false,
            secure: c.secure || false,
            sameSite: c.sameSite || 'Lax'
        })),
        origins: []  // localStorage not captured via CDP, but cookies are sufficient
    };
}

async function main() {
    console.log('=' .repeat(60));
    console.log('SeaArt Session Saver');
    console.log('=' .repeat(60));
    console.log();
    
    try {
        // Step 1: Connect to browser
        console.log(`Connecting to browser on port ${DEBUG_PORT}...`);
        const wsUrl = await getWebSocketUrl();
        console.log('✓ Connected to browser');
        console.log(`  WebSocket: ${wsUrl.substring(0, 50)}...`);
        console.log();
        
        // Step 2: Get all cookies
        console.log('Fetching cookies...');
        const cookies = await getAllCookies(wsUrl);
        console.log(`✓ Retrieved ${cookies.length} cookies`);
        
        // Step 3: Filter and count SeaArt cookies
        const seaartCookies = cookies.filter(c => 
            c.domain.toLowerCase().includes('seaart')
        );
        console.log(`  SeaArt cookies: ${seaartCookies.length}`);
        console.log();
        
        // Step 4: Save to file
        console.log('Saving session...');
        const session = formatForPlaywright(cookies);
        fs.writeFileSync(OUTPUT_FILE, JSON.stringify(session, null, 2));
        console.log(`✓ Saved to: ${OUTPUT_FILE}`);
        console.log();
        
        // Step 5: Verify
        if (seaartCookies.length >= 3) {
            console.log('=' .repeat(60));
            console.log('SUCCESS! Session saved.');
            console.log('=' .repeat(60));
            console.log();
            console.log('You can now run the pipeline:');
            console.log('  python seaart_pipeline.py your_video.mp4');
        } else {
            console.log('WARNING: Few SeaArt cookies found.');
            console.log('You may not be fully logged in.');
            console.log('Please login to SeaArt in the browser and run this again.');
        }
        
    } catch (error) {
        console.error();
        console.error('ERROR:', error.message);
        console.error();
        console.error('Troubleshooting:');
        console.error('1. Make sure ALL browser windows are closed first');
        console.error('2. Start the browser with remote debugging:');
        console.error('   "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe" --remote-debugging-port=9224 https://www.seaart.ai');
        console.error('3. Wait for the browser to fully load');
        console.error('4. Run this script again');
        process.exit(1);
    }
}

main();

