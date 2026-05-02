import asyncio
import aiohttp
import logging
import os
from neo4j import GraphDatabase

logger = logging.getLogger("Spiderweb-Engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | SPIDER: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

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
        query = """
        MERGE (t:Target {name: $name})
        MERGE (u:Username {value: $username})
        MERGE (e:Email {value: $email})
        MERGE (t)-[:USES_HANDLE]->(u)
        MERGE (t)-[:REGISTERED_EMAIL]->(e)
        """
        
        params = {"name": target_name, "username": username, "email": email}
        
        for i, (platform, url) in enumerate(discovered_links.items()):
            var_name = f"p{i}"
            query += f"""
            MERGE ({var_name}:{platform} {{url: $url_{i}}})
            MERGE (u)-[:ACTIVE_ON]->({var_name})
            """
            params[f"url_{i}"] = url
            
        with self.driver.session() as session:
            try:
                session.run(query, **params)
                logger.info(f"Graph Updated: Ingested {len(discovered_links)} intelligence nodes for @{username}.")
            except Exception as e:
                logger.error(f"Graph Ingestion Failed: {str(e)}")

async def check_platform(session, platform: str, url: str) -> dict:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        async with session.get(url, headers=headers, timeout=5) as response:
            if response.status == 200:
                logger.info(f"[HIT] Found active profile on {platform}: {url}")
                return {platform: url}
            else:
                return None
    except Exception:
        return None

async def async_spider_crawl(username: str) -> dict:
    platforms = {
        "GitHub": f"https://github.com/{username}",
        "GitLab": f"https://gitlab.com/{username}",
        "BitBucket": f"https://bitbucket.org/{username}/",
        "LeetCode": f"https://leetcode.com/{username}",
        "HackerRank": f"https://www.hackerrank.com/{username}",
        "Codeforces": f"https://codeforces.com/profile/{username}",
        "Replit": f"https://replit.com/@{username}",
        "TryHackMe": f"https://tryhackme.com/p/{username}",
        "HackTheBox": f"https://app.hackthebox.com/users/{username}",
        "Bugcrowd": f"https://bugcrowd.com/{username}",
        "HackerOne": f"https://hackerone.com/{username}",
        "X_Twitter": f"https://nitter.net/{username}", 
        "Reddit": f"https://www.reddit.com/user/{username}",
        "Medium": f"https://medium.com/@{username}",
        "Pinterest": f"https://in.pinterest.com/{username}/",
        "Tumblr": f"https://{username}.tumblr.com/",
        "Flickr": f"https://www.flickr.com/people/{username}/",
        "Twitch": f"https://www.twitch.tv/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Chess": f"https://www.chess.com/member/{username}",
        "Vimeo": f"https://vimeo.com/{username}",
        "Linktree": f"https://linktr.ee/{username}",
        "Pastebin": f"https://pastebin.com/u/{username}",
        "Behance": f"https://www.behance.net/{username}",
        "Dribbble": f"https://dribbble.com/{username}"
    }
    
    discovered_data = {}
    async with aiohttp.ClientSession() as session:
        tasks = [check_platform(session, platform, url) for platform, url in platforms.items()]
        results = await asyncio.gather(*tasks)
        for result in results:
            if result:
                discovered_data.update(result)
                
    return discovered_data

def run_osint_pipeline(name: str, username: str, email: str):
    logger.info(f"Deploying Spider Agents for target: {name}...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    discovered_data = loop.run_until_complete(async_spider_crawl(username))
    loop.close()
    
    if discovered_data:
        db_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        db_user = os.getenv("NEO4J_USER", "neo4j")
        db_pass = os.getenv("NEO4J_PASSWORD", "adminpassword")
        
        db = OSINTGraphDB(db_uri, db_user, db_pass)
        db.push_intelligence(name, username, email, discovered_data)
        db.close()
        logger.info(f"MISSION COMPLETE: Target @{username} mapped successfully.")
    else:
        logger.warning(f"MISSION FAILED: No digital footprint found for @{username}.")
