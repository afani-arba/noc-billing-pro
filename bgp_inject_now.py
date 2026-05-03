#!/usr/bin/env python3
"""
BGP Inject Now — Trigger inject cycle dengan inisialisasi MongoDB yang benar.
"""
import sys
import asyncio
import logging
import os

sys.path.insert(0, '/app')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    from core.db import init_db
    from services.bgp_steering_injector import run_inject_cycle

    logger.info("Menginisialisasi koneksi MongoDB...")
    init_db()
    logger.info("MongoDB terhubung. Memulai BGP inject cycle...")
    await run_inject_cycle()
    logger.info("BGP inject cycle selesai!")

if __name__ == '__main__':
    asyncio.run(main())
