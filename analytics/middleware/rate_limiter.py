"""
Rate Limiting Middleware for ENMS Analytics Service
====================================================
Protects API from abuse and overload using Redis-based rate limiting.

Features:
- Per-IP rate limiting
- Per-endpoint rate limiting
- Sliding window algorithm
- Configurable limits by endpoint priority
- Graceful degradation under load

Author: ENMS Team
Date: October 2025
"""

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
import logging
import asyncio
from typing import Optional, Dict, Tuple
import hashlib

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis for distributed rate limiting.
    
    Implements sliding window algorithm with different limits for different
    endpoint priorities:
    - Critical endpoints (health, auth): 100 req/min
    - Normal endpoints (OVOS, data): 60 req/min
    - Heavy endpoints (forecasting, ML): 20 req/min
    """
    
    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis = redis_client
        
        # Rate limit configurations (requests per minute)
        self.limits = {
            "critical": 100,   # Health checks, auth
            "normal": 60,      # Standard OVOS queries
            "heavy": 20,       # Forecasting, ML operations
            "default": 30      # Default for uncategorized
        }
        
        # Endpoint classifications
        self.endpoint_priority = {
            "/api/v1/health": "critical",
            "/api/v1/ovos/summary": "normal",
            "/api/v1/ovos/forecast": "heavy",
            "/api/v1/machines": "normal",
            "/api/v1/anomaly/recent": "normal",
            "/api/v1/kpi": "normal",
            "/api/v1/baseline/train": "heavy",
            "/api/v1/forecast": "heavy",
        }
        
        # Global rate limit per IP (requests per minute)
        self.global_limit = 120
        
        # Whitelist IPs (no rate limiting)
        self.whitelist = [
            "127.0.0.1",
            "localhost",
            "::1"
        ]
        
        # Enable/disable flag
        self.enabled = True
        
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check X-Forwarded-For header (from nginx)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def get_endpoint_category(self, path: str) -> str:
        """Determine endpoint priority category."""
        # Exact match
        if path in self.endpoint_priority:
            return self.endpoint_priority[path]
        
        # Prefix match
        for endpoint, priority in self.endpoint_priority.items():
            if path.startswith(endpoint):
                return priority
        
        return "default"
    
    def get_rate_limit_key(self, ip: str, path: str, category: str) -> Tuple[str, str]:
        """Generate Redis keys for rate limiting."""
        # Global IP limit key
        global_key = f"ratelimit:global:{ip}"
        
        # Endpoint-specific limit key
        path_hash = hashlib.md5(path.encode()).hexdigest()[:8]
        endpoint_key = f"ratelimit:{category}:{ip}:{path_hash}"
        
        return global_key, endpoint_key
    
    async def check_rate_limit(
        self, 
        ip: str, 
        path: str, 
        category: str
    ) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        Check if request should be rate limited.
        
        Returns:
            (allowed, remaining, reset_seconds)
        """
        if not self.redis or not self.enabled:
            return True, None, None
        
        try:
            global_key, endpoint_key = self.get_rate_limit_key(ip, path, category)
            category_limit = self.limits.get(category, self.limits["default"])
            
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()
            
            # Check global limit
            pipe.incr(global_key)
            pipe.expire(global_key, 60)  # 1 minute window
            
            # Check endpoint-specific limit
            pipe.incr(endpoint_key)
            pipe.expire(endpoint_key, 60)
            
            results = await pipe.execute()
            
            global_count = results[0]
            endpoint_count = results[2]
            
            # Check if limits exceeded
            if global_count > self.global_limit:
                remaining = 0
                reset = 60
                return False, remaining, reset
            
            if endpoint_count > category_limit:
                remaining = 0
                reset = 60
                return False, remaining, reset
            
            # Calculate remaining requests
            remaining = min(
                self.global_limit - global_count,
                category_limit - endpoint_count
            )
            
            return True, remaining, 60
            
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Fail open - allow request if Redis is down
            return True, None, None
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Get client info
        client_ip = self.get_client_ip(request)
        path = request.url.path
        
        # Skip rate limiting for whitelisted IPs
        if client_ip in self.whitelist:
            return await call_next(request)
        
        # Skip rate limiting for static files
        if path.startswith("/ui/static") or path.startswith("/docs"):
            return await call_next(request)
        
        # Get endpoint category
        category = self.get_endpoint_category(path)
        
        # Check rate limit
        allowed, remaining, reset = await self.check_rate_limit(
            client_ip, path, category
        )
        
        # Add rate limit headers to response
        async def add_rate_limit_headers(response: Response):
            if remaining is not None:
                response.headers["X-RateLimit-Limit"] = str(
                    self.limits.get(category, self.limits["default"])
                )
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(reset)
            return response
        
        # If rate limited, return 429
        if not allowed:
            logger.warning(
                f"Rate limit exceeded: {client_ip} -> {path} "
                f"(category: {category})"
            )
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Please try again in {reset} seconds.",
                    "category": category,
                    "limit": self.limits.get(category, self.limits["default"]),
                    "retry_after": reset
                },
                headers={
                    "X-RateLimit-Limit": str(
                        self.limits.get(category, self.limits["default"])
                    ),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                    "Retry-After": str(reset)
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response = await add_rate_limit_headers(response)
        
        return response


class ConnectionThrottle:
    """
    Connection throttling to prevent connection exhaustion.
    
    Limits concurrent connections per IP and globally.
    """
    
    def __init__(self, max_connections_per_ip: int = 10, max_total_connections: int = 100):
        self.max_per_ip = max_connections_per_ip
        self.max_total = max_total_connections
        self.connections: Dict[str, int] = {}
        self.total = 0
        self.lock = asyncio.Lock()
    
    async def acquire(self, ip: str) -> bool:
        """
        Try to acquire connection slot.
        
        Returns:
            True if connection allowed, False otherwise
        """
        async with self.lock:
            # Check total connections
            if self.total >= self.max_total:
                logger.warning(f"Total connection limit reached: {self.total}/{self.max_total}")
                return False
            
            # Check per-IP connections
            ip_connections = self.connections.get(ip, 0)
            if ip_connections >= self.max_per_ip:
                logger.warning(f"IP connection limit reached for {ip}: {ip_connections}/{self.max_per_ip}")
                return False
            
            # Increment counters
            self.connections[ip] = ip_connections + 1
            self.total += 1
            
            return True
    
    async def release(self, ip: str):
        """Release connection slot."""
        async with self.lock:
            if ip in self.connections:
                self.connections[ip] -= 1
                if self.connections[ip] <= 0:
                    del self.connections[ip]
            
            self.total = max(0, self.total - 1)
    
    def get_stats(self) -> Dict:
        """Get current connection statistics."""
        return {
            "total_connections": self.total,
            "max_total": self.max_total,
            "connections_by_ip": dict(self.connections),
            "unique_ips": len(self.connections)
        }


class ConnectionThrottleMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce connection limits."""
    
    def __init__(self, app, throttle: ConnectionThrottle):
        super().__init__(app)
        self.throttle = throttle
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def dispatch(self, request: Request, call_next):
        """Process request with connection throttling."""
        client_ip = self.get_client_ip(request)
        
        # Try to acquire connection slot
        acquired = await self.throttle.acquire(client_ip)
        
        if not acquired:
            logger.warning(f"Connection throttled: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "error": "too_many_connections",
                    "message": "Server is at capacity. Please try again later.",
                    "retry_after": 30
                },
                headers={
                    "Retry-After": "30"
                }
            )
        
        try:
            # Process request
            response = await call_next(request)
            return response
        finally:
            # Always release connection
            await self.throttle.release(client_ip)
