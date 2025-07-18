"""
Configuration settings for the TACO application
"""
from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    # Backlog Configuration
    backlog_space_key: str
    backlog_api_key: str
    backlog_project_ids: str  # Comma-separated list of project IDs

    # Slack Configuration
    slack_bot_token: str
    slack_app_token: str
    slack_channel_id: str
    slack_admin_user_id: str

    # AI Configuration (Gemini or Bedrock)
    ai_provider: str = "gemini"  # "gemini" or "bedrock"
    ai_api_key: str
    ai_model: str = "gemini-pro"  # Default model for Gemini

    # System Configuration
    timezone: str = "Asia/Tokyo"
    log_level: str = "INFO"
    database_url: str = "sqlite:///taco.db"
    cache_ttl_minutes: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_backlog_project_ids_list(self) -> List[str]:
        """
        Parse the comma-separated project IDs into a list
        """
        if not self.backlog_project_ids:
            return []
        return [pid.strip() for pid in self.backlog_project_ids.split(",")]

    def validate_configuration(self) -> dict:
        """
        Validate the configuration and return any issues
        """
        issues = {}
        
        # Check Backlog configuration
        if not self.backlog_space_key:
            issues["backlog_space_key"] = "Backlog space key is required"
        if not self.backlog_api_key:
            issues["backlog_api_key"] = "Backlog API key is required"
        if not self.backlog_project_ids:
            issues["backlog_project_ids"] = "At least one Backlog project ID is required"
            
        # Check Slack configuration
        if not self.slack_bot_token:
            issues["slack_bot_token"] = "Slack bot token is required"
        if not self.slack_app_token:
            issues["slack_app_token"] = "Slack app token is required"
        if not self.slack_channel_id:
            issues["slack_channel_id"] = "Slack channel ID is required"
        if not self.slack_admin_user_id:
            issues["slack_admin_user_id"] = "Slack admin user ID is required"
            
        # Check AI configuration
        if not self.ai_api_key:
            issues["ai_api_key"] = f"{self.ai_provider.capitalize()} API key is required"
        if self.ai_provider not in ["gemini", "bedrock"]:
            issues["ai_provider"] = "AI provider must be 'gemini' or 'bedrock'"
            
        return issues


@lru_cache()
def get_settings() -> Settings:
    """
    Create and cache settings instance
    """
    return Settings()