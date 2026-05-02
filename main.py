import os
import logging
from datetime import datetime
from io import BytesIO
from fastapi import FastAPI, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# --- ADVANCED PDF & BRANDING IMPORTS ---
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
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

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

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
    """Pulls archived targets from the Neo4j database."""
    try:
        db = OSINTGraphDB("bolt://localhost:7687", "neo4j", "adminpassword")
        query = """
        MATCH (t:Target)-[:USES_HANDLE]->(u:Username)
        RETURN t.name as name, u.value as username
        ORDER BY t.name DESC LIMIT 20
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
    username: str = Query(...), 
    password: str = Query(None)
):
    """Generates the enterprise-grade intelligence PDF directly to memory."""
    try:
        # 1. Fetch Intelligence
        db = OSINTGraphDB("bolt://localhost:7687", "neo4j", "adminpassword")
        query = """
        MATCH (u:Username {value: $username})-[r]->(n) 
        RETURN type(r) as rel, coalesce(n.value, n.url, 'N/A') as val
        """
        with db.driver.session() as session:
            results = session.run(query, username=username)
            data_points = results.data()
        db.close()
    except Exception as e:
        logger.error(f"DB Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Intelligence Database Offline")

    try:
        # 2. Use BytesIO to create PDF in RAM (Avoids local file permission errors)
        buffer = BytesIO()
        
        # Default password is set to your academic ID if none provided
        encryption_key = password if password else "25BCE11382"
        enc = StandardEncryption(encryption_key, canPrint=1)
        
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4, 
            encrypt=enc,
            rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50
        )
        
        styles = getSampleStyleSheet()
        elements = []

        # --- BRANDING SECTION ---
        # Note: Using HexColor (Capital 'H' and 'C') to resolve previous attribute error
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor("#22d3ee"), 
            alignment=TA_CENTER,
            spaceAfter=5
        )
        elements.append(Paragraph("SPIDERWEB CORE", title_style))
        
        subtitle_style = ParagraphStyle(
            'SubStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.gray,
            alignment=TA_CENTER,
            spaceAfter=25
        )
        elements.append(Paragraph(f"INTELLIGENCE DOSSIER: @{username}", subtitle_style))

        # --- DATA TABLE SECTION ---
        if data_points:
            table_data = [["NODE RELATION", "DISCOVERED INTELLIGENCE"]]
            for item in data_points:
                rel_label = item['rel'].replace("_", " ")
                table_data.append([rel_label, item['val']])
            
            osint_table = Table(table_data, colWidths=[140, 320])
            osint_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")), 
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(osint_table)
        else:
            elements.append(Paragraph("No linked intelligence found in the graph.", styles['Italic']))

        # --- FOOTER ---
        elements.append(Spacer(1, 40))
        footer_text = f"CONFIDENTIAL | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        elements.append(Paragraph(footer_text, styles['Normal']))

        # 3. Build and Stream directly to browser
        doc.build(elements)
        buffer.seek(0)
        
        return StreamingResponse(
            buffer, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Dossier_{username}.pdf"}
        )

    except Exception as e:
        logger.error(f"Report Generation Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Engine Error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)