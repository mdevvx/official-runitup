from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from utils.logger import get_logger

logger = get_logger(__name__)


class SupabaseClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = None
        return cls._instance

    def initialize(self) -> Client:
        """Initialize Supabase client"""
        try:
            if self.client is None:
                self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info("✅ Supabase client initialized successfully")
            return self.client
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")
            raise

    def get_client(self) -> Client:
        """Get Supabase client instance"""
        if self.client is None:
            return self.initialize()
        return self.client


# Global instance
supabase_client = SupabaseClient()


def get_supabase() -> Client:
    """Helper function to get Supabase client"""
    return supabase_client.get_client()
