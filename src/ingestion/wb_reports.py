from datetime import datetime, timedelta
from typing import Optional, List, Dict
from .wb_client import fetch_report

class WBReports:

    BASE_URL = "https://suppliers-stats.wildberries.ru/api/v1"

    # коэффиценты приемки
    @staticmethod
    def get_coefficients(date_from: str, date_to: Optional[str] = None,
                         limit: int = 100000) -> List[Dict]:
        endpoint = f"{WBReports.BASE_URL}/acceptance/coefficients"
        params = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": limit
        } 
        return fetch_report(endpoint, params)
    
    
    
