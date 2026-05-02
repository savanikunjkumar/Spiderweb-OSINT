import asyncio
import aiohttp
import logging
from neo4j import GraphDatabase

# ==========================================
# 1. ENTERPRISE LOGGING SETUP
# ==========================================
logger = logging.getLogger("Spiderweb-Engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | SPIDER: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ==========================================
# 2. NEO4J GRAPH DATABASE HANDLER
# ==========================================
class OSINTGraphDB:
    def __init__(self, uri, user, password):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info("Graph Database connection established.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {str(e)}")

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Graph Database connection closed.")

    def push_intelligence(self, target_name: str, username: str, email: str, discovered_links: dict):
        """Merges discovered data into the Neo4j Graph using unique identifiers."""
        # Clean labels to remove special characters for Cypher compatibility
        query = """
        MERGE (t:Target {name: $name})
        MERGE (u:Username {value: $username})
        MERGE (e:Email {value: $email})
        MERGE (t)-[:USES_HANDLE]->(u)
        MERGE (t)-[:REGISTERED_EMAIL]->(e)
        """
        
        params = {"name": target_name, "username": username, "email": email}
        
        for i, (platform, url) in enumerate(discovered_links.items()):
            # Use a generic 'Platform' label with a 'type' property for better query performance
            query += f"""
            MERGE (p{i}:Platform {{type: $type_{i}, url: $url_{i}}})
            MERGE (u)-[:ACTIVE_ON]->(p{i})
            """
            params[f"type_{i}"] = platform
            params[f"url_{i}"] = url
            
        with self.driver.session() as session:
            try:
                session.run(query, **params)
                logger.info(f"Graph Updated: Ingested {len(discovered_links)} verified nodes for @{username}.")
            except Exception as e:
                logger.error(f"Graph Ingestion Failed: {str(e)}")

# ==========================================
# 3. ASYNCHRONOUS OSINT SCRAPER (WITH VERIFICATION)
# ==========================================
async def check_platform(session, platform: str, url: str, username: str) -> dict:
    """Checks and VERIFIES if a profile exists by scanning page content."""
    
    # Phrases that indicate a "200 OK" page is actually a "Not Found" page
    error_indicators = [
        "page not found", "user not found", "nobody on reddit", 
        "could not be found", "doesn't exist", "does not exist",
        "create an account", "join today", "signup", "sign up", "404"
    ]
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Spider/1.0'}
        async with session.get(url, headers=headers, timeout=7, allow_redirects=True) as response:
            if response.status == 200:
                content = (await response.text()).lower()
                
                # VERIFICATION 1: Does the target username actually appear in the HTML?
                if username.lower() not in content:
                    return None
                
                # VERIFICATION 2: Does the page contain "Not Found" keywords?
                for error in error_indicators:
                    if error in content:
                        # Ignore the error if it's just part of the platform's name/footer
                        if error not in platform.lower():
                            return None

                logger.info(f"[HIT] Verified profile on {platform}: {url}")
                return {platform: url}
            return None
    except Exception:
        return None

async def async_spider_crawl(username: str) -> dict:
    """The core engine that checks multiple platforms concurrently."""
    platforms = {
        "GitHub": f"https://github.com/{username}",
        "GitLab": f"https://gitlab.com/{username}",
        "LeetCode": f"https://leetcode.com/{username}",
        "HackerRank": f"https://www.hackerrank.com/{username}",
        "Codeforces": f"https://codeforces.com/profile/{username}",
        "TryHackMe": f"https://tryhackme.com/p/{username}",
        "HackTheBox": f"https://app.hackthebox.com/users/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}",
        "Medium": f"https://medium.com/@{username}",
        "Twitch": f"https://www.twitch.tv/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Chess": f"https://www.chess.com/member/{username}",
        "Linktree": f"https://linktr.ee/{username}"
    }
    
    discovered_data = {}
    async with aiohttp.ClientSession() as session:
        # Pass the username to check_platform for verification logic
        tasks = [check_platform(session, p, u, username) for p, u in platforms.items()]
        results = await asyncio.gather(*tasks)
        for result in results:
            if result:
                discovered_data.update(result)
                
    return discovered_data

# ==========================================
# 4. THE PIPELINE EXECUTOR 
# ==========================================
def run_osint_pipeline(name: str, username: str, email: str):
    logger.info(f"Deploying Verified Spider Agents for target: {name}...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    discovered_data = loop.run_until_complete(async_spider_crawl(username))
    loop.close()
    
    if discovered_data:
        # Ensure 'adminpassword' matches your Neo4j Desktop settings
        db = OSINTGraphDB("bolt://localhost:7687", "neo4j", "adminpassword")
        db.push_intelligence(name, username, email, discovered_data)
        db.close()
        logger.info(f"MISSION COMPLETE: Target @{username} mapped with verified hits.")
    else:
        logger.warning(f"MISSION FAILED: No verified footprint found for @{username}.")