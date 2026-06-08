"""
Analytics UI Routes
===================
FastAPI routes for serving the analytics dashboard UI.

These routes serve Jinja2 templates for:
- Dashboard overview
- Baseline regression training
- Anomaly viewer
- KPI visualization
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import logging

logger = logging.getLogger(__name__)

# Headers to prevent caching
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0"
}

# Create router
router = APIRouter(prefix="/ui", tags=["UI"])

# Configure Jinja2 templates
templates = Jinja2Templates(directory="/app/ui/templates")


@router.get("/", response_class=HTMLResponse, name="ui_dashboard")
async def dashboard(request: Request):
    """
    Analytics Dashboard - Main UI landing page
    
    Shows:
    - Service status overview
    - Recent anomalies
    - Quick action buttons
    - System information
    """
    response = templates.TemplateResponse("dashboard.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/websocket-test", response_class=HTMLResponse, name="websocket_test")
async def websocket_test(request: Request):
    """
    WebSocket Connection Test Page
    
    Diagnostic tool for testing:
    - WebSocket connectivity
    - Real-time event delivery
    - Message handling
    """
    response = templates.TemplateResponse("websocket-test.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/baseline", response_class=HTMLResponse, name="ui_baseline")
async def baseline_ui(request: Request):
    """
    Baseline Training UI
    
    Provides interface for:
    - Machine selection
    - Date range selection
    - Driver (feature) selection
    - Model training execution
    - Results visualization (R², coefficients, charts)
    """
    return templates.TemplateResponse("baseline.html", {"request": request})


@router.get("/anomaly", response_class=HTMLResponse, name="ui_anomaly")
async def anomaly_ui(request: Request):
    """
    Anomaly Viewer UI
    
    Features:
    - Anomaly filtering (machine, time, severity, status)
    - Detection trigger
    - Anomaly resolution
    - Severity indicators
    """
    return templates.TemplateResponse("anomaly.html", {"request": request})


@router.get("/anomaly-creator", response_class=HTMLResponse, name="ui_anomaly_creator")
async def anomaly_creator_ui(request: Request):
    """
    Anomaly Creator UI - Development Tool
    
    Features:
    - Create test anomalies manually
    - Helpful tooltips for each field
    - Quick-fill buttons for common scenarios
    - Real-time validation
    
    ⚠️ FOR DEVELOPMENT AND TESTING ONLY
    """
    response = templates.TemplateResponse("anomaly-creator.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/kpi", response_class=HTMLResponse, name="ui_kpi")
async def kpi_ui(request: Request):
    """
    KPI Dashboard UI
    
    Displays:
    - All 5 KPIs (SEC, Peak Demand, Load Factor, Cost, Carbon)
    - Interactive charts
    - Time range selection
    - Export functionality
    """
    response = templates.TemplateResponse("kpi.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/forecast", response_class=HTMLResponse, name="ui_forecast")
async def forecast_ui(request: Request):
    """
    Forecast UI
    
    Features:
    - ARIMA & Prophet model training
    - Short/medium/long-term forecasting
    - Confidence interval visualization
    - Optimal load scheduling
    - Model status tracking
    """
    return templates.TemplateResponse("forecast.html", {"request": request})


@router.get("/sankey", response_class=HTMLResponse, name="ui_sankey")
async def sankey_ui(request: Request):
    """
    Sankey Energy Flow Diagram UI (Phase 4 Session 3)
    
    Visualizes energy flow hierarchy:
    - Grid → Factories → Departments → Machines
    - Interactive drill-down capability
    - Real-time flow visualization
    - Color-coded by energy intensity
    - D3.js powered visualization
    """
    response = templates.TemplateResponse("sankey.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/heatmap", response_class=HTMLResponse, name="ui_heatmap")
async def heatmap_ui(request: Request):
    """
    Anomaly Heatmap UI (Phase 4 Session 3)
    
    Features:
    - Hour-of-day × Machine heatmap
    - Day-of-week × Machine heatmap
    - Pattern identification (automatic insights)
    - Color intensity by anomaly frequency
    - Interactive tooltips with severity data
    - Chart.js matrix visualization
    """
    response = templates.TemplateResponse("heatmap.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/comparison", response_class=HTMLResponse, name="ui_comparison")
async def comparison_ui(request: Request):
    """
    Machine Comparison UI (Phase 4 Session 3)
    
    Features:
    - Side-by-side comparison of 2-5 machines
    - Energy consumption benchmarking
    - Efficiency metrics (SEC, load factor)
    - Cost analysis and potential savings
    - Production output comparison
    - Performance rankings (best to worst)
    - Interactive comparison charts
    - Automated insights and recommendations
    """
    response = templates.TemplateResponse("comparison.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/model-performance", response_class=HTMLResponse, name="ui_model_performance")
async def model_performance_ui(request: Request):
    """
    Model Performance Tracking UI (Phase 4 Session 4)
    
    Features:
    - ML model performance monitoring over time
    - Drift detection and alerts (data drift, concept drift)
    - Auto-retraining triggers (manual and automatic)
    - A/B testing between model versions
    - Performance metrics (R², RMSE, MAE, MAPE, precision, recall, F1)
    - Training history and version tracking
    - Real-time alerts for degraded performance
    - Model comparison analytics
    - Interactive charts for trend analysis
    - Configurable thresholds and automated actions
    """
    response = templates.TemplateResponse("model_performance.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


@router.get("/components-demo", response_class=HTMLResponse, name="ui_components_demo")
async def components_demo_ui(request: Request):
    """
    Component Library Demo Page (Phase 6 - Milestone 6.1)
    
    Interactive showcase for all v3 frontend components:
    - LoadingSpinner (3 sizes, inline/overlay modes)
    - ErrorMessage (4 types: error, warning, info, success)
    - SEUSelector (single/multi-select modes)
    - EnergySourceFilter (auto-select, radio, checkbox modes)
    - ChartContainer (Chart.js integration, export PNG/CSV)
    - LoadingOrchestrator (progressive loading demo)
    - APIClient (retry logic, caching, error handling)
    
    ⚠️ FOR DEVELOPMENT AND TESTING ONLY
    Access: http://<SERVER_IP>:8080/analytics/ui/components-demo
    """
    response = templates.TemplateResponse("components-demo.html", {"request": request})
    response.headers.update(NO_CACHE_HEADERS)
    return response


# Health check for UI service
@router.get("/health", response_class=HTMLResponse)
async def ui_health(request: Request):
    """UI service health check"""
    return HTMLResponse(content="<h1>Analytics UI is healthy</h1>", status_code=200)