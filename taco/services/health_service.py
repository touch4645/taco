"""
Health check service for monitoring system components
"""
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass
import logging
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import sqlite3

from taco.config.settings import get_settings

logger = logging.getLogger(__name__)

@dataclass
class ServiceHealth:
    """
    Health status of an individual service
    """
    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    last_checked: datetime
    details: Optional[Dict] = None


@dataclass
class HealthStatus:
    """
    Overall health status of the system
    """
    status: str  # "healthy", "degraded", "unhealthy"
    services: Dict[str, ServiceHealth]
    timestamp: datetime


class HealthChecker:
    """
    Service for checking the health of system components
    """
    def __init__(self):
        self.settings = get_settings()
        
    def check_all(self) -> HealthStatus:
        """
        Check the health of all system components
        """
        services = {}
        services["backlog"] = self.check_backlog_connectivity()
        services["slack"] = self.check_slack_connectivity()
        services["database"] = self.check_database_connectivity()
        services["ai"] = self.check_ai_connectivity()
        
        # Determine overall status
        if any(s.status == "unhealthy" for s in services.values()):
            status = "unhealthy"
        elif any(s.status == "degraded" for s in services.values()):
            status = "degraded"
        else:
            status = "healthy"
            
        return HealthStatus(
            status=status,
            services=services,
            timestamp=datetime.now()
        )
        
    def check_backlog_connectivity(self) -> ServiceHealth:
        """
        Check connectivity to Backlog API
        """
        try:
            # Simple API call to check connectivity - using query parameter for API key
            url = f"https://{self.settings.backlog_space_key}.backlog.com/api/v2/space?apiKey={self.settings.backlog_api_key}"
            
            logger.debug(f"Backlog API URL: {url}")
            logger.debug(f"Backlog API Key (最初の5文字): {self.settings.backlog_api_key[:5]}...")
            
            response = requests.get(url, timeout=5)
            
            logger.debug(f"Backlog API Response: {response.status_code}")
            if response.status_code != 200:
                logger.debug(f"Backlog API Response Body: {response.text[:100]}")
            
            if response.status_code == 200:
                return ServiceHealth(
                    status="healthy",
                    message="Successfully connected to Backlog API",
                    last_checked=datetime.now()
                )
            else:
                return ServiceHealth(
                    status="unhealthy",
                    message=f"Failed to connect to Backlog API: HTTP {response.status_code}",
                    last_checked=datetime.now(),
                    details={"status_code": response.status_code}
                )
        except Exception as e:
            logger.error(f"Backlog connectivity check failed: {str(e)}")
            return ServiceHealth(
                status="unhealthy",
                message=f"Failed to connect to Backlog API: {str(e)}",
                last_checked=datetime.now(),
                details={"error": str(e)}
            )
            
    def check_slack_connectivity(self) -> ServiceHealth:
        """
        Check connectivity to Slack API
        """
        try:
            client = WebClient(token=self.settings.slack_bot_token)
            response = client.auth_test()
            
            if response["ok"]:
                return ServiceHealth(
                    status="healthy",
                    message=f"Successfully connected to Slack as {response['user']}",
                    last_checked=datetime.now(),
                    details={"team": response["team"], "user": response["user"]}
                )
            else:
                return ServiceHealth(
                    status="unhealthy",
                    message="Failed to authenticate with Slack API",
                    last_checked=datetime.now()
                )
        except SlackApiError as e:
            logger.error(f"Slack connectivity check failed: {str(e)}")
            return ServiceHealth(
                status="unhealthy",
                message=f"Failed to connect to Slack API: {str(e)}",
                last_checked=datetime.now(),
                details={"error": str(e)}
            )
        except Exception as e:
            logger.error(f"Slack connectivity check failed: {str(e)}")
            return ServiceHealth(
                status="unhealthy",
                message=f"Failed to connect to Slack API: {str(e)}",
                last_checked=datetime.now(),
                details={"error": str(e)}
            )
            
    def check_database_connectivity(self) -> ServiceHealth:
        """
        Check connectivity to the database
        """
        try:
            if self.settings.database_url.startswith("sqlite"):
                # For SQLite, just try to create a connection
                db_path = self.settings.database_url.replace("sqlite:///", "")
                conn = sqlite3.connect(db_path)
                conn.execute("SELECT 1")
                conn.close()
                
                return ServiceHealth(
                    status="healthy",
                    message="Successfully connected to SQLite database",
                    last_checked=datetime.now()
                )
            else:
                # For other databases, we would need to implement specific checks
                return ServiceHealth(
                    status="degraded",
                    message="Database connectivity check not implemented for this database type",
                    last_checked=datetime.now(),
                    details={"database_type": self.settings.database_url.split(":")[0]}
                )
        except Exception as e:
            logger.error(f"Database connectivity check failed: {str(e)}")
            return ServiceHealth(
                status="unhealthy",
                message=f"Failed to connect to database: {str(e)}",
                last_checked=datetime.now(),
                details={"error": str(e)}
            )
            
    def check_ai_connectivity(self) -> ServiceHealth:
        """
        Check connectivity to AI API (Gemini or Bedrock)
        """
        try:
            if self.settings.ai_provider == "gemini":
                # Check Gemini API
                import google.generativeai as genai
                
                genai.configure(api_key=self.settings.ai_api_key)
                model = genai.GenerativeModel(self.settings.ai_model)
                response = model.generate_content("Hello")
                
                if response:
                    return ServiceHealth(
                        status="healthy",
                        message="Successfully connected to Gemini API",
                        last_checked=datetime.now()
                    )
                else:
                    return ServiceHealth(
                        status="degraded",
                        message="Connected to Gemini API but received empty response",
                        last_checked=datetime.now()
                    )
            elif self.settings.ai_provider == "bedrock":
                # For Bedrock, we would need AWS SDK
                # This is a placeholder for now
                return ServiceHealth(
                    status="degraded",
                    message="Bedrock API connectivity check not implemented yet",
                    last_checked=datetime.now()
                )
            else:
                return ServiceHealth(
                    status="unhealthy",
                    message=f"Unknown AI provider: {self.settings.ai_provider}",
                    last_checked=datetime.now()
                )
        except Exception as e:
            logger.error(f"AI API connectivity check failed: {str(e)}")
            return ServiceHealth(
                status="unhealthy",
                message=f"Failed to connect to {self.settings.ai_provider.capitalize()} API: {str(e)}",
                last_checked=datetime.now(),
                details={"error": str(e)}
            )