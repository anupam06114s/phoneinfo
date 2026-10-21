from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import os
import math
import duckdb
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Configure DuckDB with low memory footprint suitable for free-tier deployments
con = duckdb.connect(config={
    'max_memory': '250MB',
    'threads': '2',
    'enable_object_cache': 'false',
    'preserve_insertion_order': 'false'
})
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
HF_DATASET = os.getenv("HF_DATASET", "MRSHREY197/hitek-3digit-rah").strip()

if HF_TOKEN:
    try:
        con.execute(f"""
            CREATE OR REPLACE SECRET hf_secret (
                TYPE HUGGINGFACE,
                TOKEN '{HF_TOKEN}'
            );
        """)
        print("[INFO] Configured DuckDB with Hugging Face Token.")
    except Exception as err:
        print(f"[WARN] Could not set HF secret: {err}")

LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hitek Data Gateway - LIVE</title>
    <style>
        body { margin: 0; overflow: hidden; background-color: #050505; color: #00ffcc; font-family: 'Courier New', Courier, monospace; }
        #canvas-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; }
        .overlay { 
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); 
            text-align: center; background: rgba(10, 10, 10, 0.85); padding: 50px; 
            border: 1px solid #00ffcc; border-radius: 12px; box-shadow: 0 0 30px rgba(0, 255, 204, 0.3); 
            backdrop-filter: blur(5px);
        }
        h1 { margin: 0 0 15px 0; font-size: 3.5em; text-transform: uppercase; letter-spacing: 6px; text-shadow: 0 0 15px #00ffcc; }
        p { font-size: 1.2em; margin: 8px 0; color: #ccc; }
        .highlight { color: #00ffcc; font-weight: bold; }
        .status-box { 
            margin-top: 30px; font-weight: bold; padding: 15px; 
            border-radius: 8px; background: rgba(0, 255, 204, 0.1); 
            border: 1px solid rgba(0, 255, 204, 0.5);
            font-size: 1.1em;
        }
        .blinking { animation: blinker 1.5s linear infinite; display: inline-block; }
        @keyframes blinker { 50% { opacity: 0; } }
    </style>
</head>
<body>
    <div id="canvas-container"></div>
    <div class="overlay">
        <h1>SYSTEM ONLINE</h1>
        <p>API Gateway is <span class="highlight">Active & Secured</span></p>
        <p>Parquet Cloud Engine: <span class="highlight">Connected</span></p>
        <div class="status-box">
            <span class="blinking" style="color: #00ffcc;">●</span> HTTP 200 OK - LISTENING FOR QUERIES
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 2000);
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.getElementById('canvas-container').appendChild(renderer.domElement);

        const geometry = new THREE.BufferGeometry();
        const vertices = [];
        for (let i = 0; i < 8000; i++) {
            vertices.push(THREE.MathUtils.randFloatSpread(3000));
            vertices.push(THREE.MathUtils.randFloatSpread(3000));
            vertices.push(THREE.MathUtils.randFloatSpread(3000));
        }
        
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        const material = new THREE.PointsMaterial({ color: 0x00ffcc, size: 2.5, transparent: true, opacity: 0.8 });
        const points = new THREE.Points(geometry, material);
        scene.add(points);

        camera.position.z = 1200;

        function animate() {
            requestAnimationFrame(animate);
            points.rotation.x += 0.0005;
            points.rotation.y += 0.001;
            renderer.render(scene, camera);
        }
        animate();

        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
    </script>
</body>
</html>
"""

def sanitize_value(val):
    """Safely convert NaNs, Infinities, and whitespace-padded strings to JSON-compliant values."""
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    return str(val)

def query_parquet_shard(url: str, filter_col: str, number: str):
    """Query a single parquet shard using low memory fetchall and return cleaned list of dicts."""
    query = f"""
        SELECT mobile, name, fname, address, alt, circle, id, email 
        FROM read_parquet('{url}') 
        WHERE TRIM({filter_col}) = '{number}' OR {filter_col} IN ('{number}', ' {number} ')
    """
    rel = con.execute(query)
    cols = [d[0] for d in rel.description]
    rows = rel.fetchall()
    
    result = []
    for row in rows:
        row_dict = {}
        for col_name, val in zip(cols, row):
            row_dict[col_name] = sanitize_value(val)
        result.append(row_dict)
    return result

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "status": "rejected",
                "message": "Invalid endpoint. STRICTLY use /FetchData?Number=XXXXXXXXXX",
                "Developer": "@anupam"
            }
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "Developer": "@anupam"}
    )

@app.get("/", response_class=HTMLResponse)
def root_landing_page():
    return HTMLResponse(content=LANDING_PAGE_HTML, status_code=200)

@app.get("/FetchData")
def fetch_data(Number: str = Query(None)):
    if not Number:
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": "Invalid parameter. STRICTLY use /FetchData?Number=XXXXXXXXXX",
                "Developer": "@anupam"
            }
        )
    
    clean_number = Number.strip()
    if not clean_number.isdigit() or len(clean_number) < 10 or len(clean_number) > 15:
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": "Invalid parameter. STRICTLY use /FetchData?Number=XXXXXXXXXX",
                "Developer": "@anupam"
            }
        )
    
    # 3-digit shard routing (e.g. 027 for numbers ending in 027)
    shard_id = clean_number[-3:]
    
    primary_url = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main/main_shard_{shard_id}.parquet"
    alt_url = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main/alt_shard_{shard_id}.parquet"
    
    try:
        # 1. Query Main Shard
        main_records = query_parquet_shard(primary_url, "mobile", clean_number)
        
        # 2. Query Alt Shard
        alt_records = query_parquet_shard(alt_url, "alt", clean_number)
        
        if not main_records and not alt_records:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found", 
                    "phone": clean_number,
                    "Developer": "@anupam"
                }
            )
            
        return JSONResponse(
            status_code=200,
            content={
                "status": "success", 
                "phone": clean_number,
                "Data": {
                    "Main_Records": main_records,
                    "Alt_Records": alt_records
                },
                "Developer": "@anupam"
            }
        )
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Database processing error: {str(e)}",
                "Developer": "@anupam"
            }
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
