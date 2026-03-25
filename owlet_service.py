"""
Owlet device discovery and interaction service.

This module provides utilities for authenticating with the Owlet API
and discovering available Smart Sock devices.
"""

import logging
from pyowletapi.sock import Sock

logger = logging.getLogger(__name__)


async def discover_socks(api):
    """
    Discover Owlet Smart Sock devices connected to the account.
    
    Args:
        api: Authenticated OwletAPI instance
        
    Returns:
        List of Sock objects representing SS3 (Smart Sock 3) devices
    """
    logger.info("Discovering socks...")
    devices_resp = await api.get_devices()
    socks = []
    
    # Handle both list and dict responses
    devices_list = []
    if isinstance(devices_resp, list):
        # API returned list directly
        devices_list = devices_resp
    elif isinstance(devices_resp, dict) and "response" in devices_resp:
        # API returned dict with "response" key
        devices_list = devices_resp["response"]
    
    for entry in devices_list:
        dev = entry.get("device")
        if not dev:
            continue
        oem_model = (dev.get("oem_model") or "").lower()
        if "ss3" in oem_model: 
            socks.append(Sock(api, dev))
    
    return socks
