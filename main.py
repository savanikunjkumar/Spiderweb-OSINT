import os
import logging
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# --- ADVANCED PDF IMPORTS ---
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pdfencrypt import StandardEncryption

from osint_engine import run_osint_pipeline, OSINTGraphDB
import uvicorn

# ==========================================
# 1. CONFIGURATION & LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Spiderweb-Core")

app = FastAPI(title="Spiderweb OSINT Engine", version="7.0.0")
# Enable CORS for all methods (including DELETE)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

def cleanup_report(file_path: str):
    """Deletes the PDF after download."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Garbage Collection: Wiped secure file -> {file_path}")
    except Exception as e:
        logger.error(f"Memory Leak Warning: {str(e)}")

# ==========================================
# 2. API ENDPOINTS
# ==========================================

@app.get("/scan")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    name: str = Query(...), username: str = Query(...), email: str = Query(...)
):
    logger.info(f"SCAN DEPLOYED: Target -> {name} (@{username})")
    background_tasks.add_task(run_osint_pipeline, name, username, email)
    return {"status": "success", "message": "OSINT Spider deployed", "target": username}

@app.delete("/purge")
async def purge_database():
    """Wipes all records from the Neo4j Graph Database."""
    try:
        # ⚠️ ENSURE THIS PASSWORD MATCHES YOUR NEO4J DESKTOP
        db = OSINTGraphDB("bolt://localhost:7687", "neo4j", "adminpassword") 
        
        query = "MATCH (n) DETACH DELETE n"
        with db.driver.session() as session:
            session.run(query)
        db.close()
        
        logger.info("DATABASE PURGED SUCCESSFULLY")
        return {"status": "success", "message": "Database wiped clean."}
    except Exception as e:
        logger.error(f"PURGE FAILED: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/history")
async def get_scan_history():
    """Pulls targets from the Neo4j database."""
    try:
        db = OSINTGraphDB("bolt://localhost:7687", "neo4j", "adminpassword")
        query = """
        MATCH (t:Target)-[:USES_HANDLE]->(u:Username)
        RETURN t.name as name, u.value as username
        ORDER BY t.name DESC
        LIMIT 20
        """
        with db.driver.session() as session:
            results = session.run(query)
            history = [{"name": record["name"], "user": record["username"]} for record in results]
            
        db.close()
        return {"status": "success", "history": history}
    except Exception as e:
        logger.error(f"HISTORY FETCH FAILED: {str(e)}")
        return {"status": "error", "history": []}

@app.get("/report")
async def generate_report(
    background_tasks: BackgroundTasks, username: str = Query(...), password: str = Query(None)
):
    """Generates the intelligence PDF."""
    report_path = f"OSINT_Report_{username}.pdf"
    try:
        db = OSINTGraphDB("bolt://localhost:7687", "neo4j", "adminpassword")
        query = "MATCH (u:Username {value: $username})-[r]->(n) RETURN type(r) as rel, n.value as val"
        with db.driver.session() as session:
            results = session.run(query, username=username)
            data_points = results.data()
        db.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Intelligence Database Offline")

    try:
        encryption_key = password if password else "25BCE11382"
        enc = StandardEncryption(encryption_key, canPrint=1)
        doc = SimpleDocTemplate(report_path, pagesize=letter, encrypt=enc)
        styles = getSampleStyleSheet()
        elements = [Paragraph("SPIDERWEB DOSSIER", styles['Heading1'])]
        
        # Build Table
        if data_points:
            table_data = [["NODE RELATION", "DISCOVERED VALUE"]]
            for item in data_points:
                table_data.append([item['rel'], item['val']])
            elements.append(Table(table_data))

        doc.build(elements)
        background_tasks.add_task(cleanup_report, report_path)
        return FileResponse(path=report_path, filename=f"Dossier_@{username}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Report Error")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)