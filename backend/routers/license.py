from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from core.db import get_db
from core.auth import require_admin
import services.license_service as lic_svc

router = APIRouter(prefix="/system/license", tags=["License"])

class LicenseUpdateRequest(BaseModel):
    license_key: str

@router.get("")
async def get_license_info(db=Depends(get_db)):
    """Get active license info and hardware ID."""
    doc = await db.system_settings.find_one({"_id": "license"})
    status_doc = await db.system_settings.find_one({"_id": "license_status"}) or {}
    
    return {
        "hardware_id": lic_svc.get_hardware_id(),
        "license_key": doc.get("license_key") if doc else None,
        "status": status_doc.get("status", "unlicensed"),
        "type": status_doc.get("type"),
        "edition": status_doc.get("edition") or lic_svc.EDITION,
        "customer": status_doc.get("customer"),
        "expires_at": status_doc.get("expires_at"),
        "message": status_doc.get("message")
    }

@router.post("")
async def update_license(req: LicenseUpdateRequest, db=Depends(get_db)):
    """Save new license key and verify immediately."""
    await db.system_settings.update_one(
        {"_id": "license"},
        {"$set": {"license_key": req.license_key}},
        upsert=True
    )
    
    # Trigger immediate verification
    is_valid = await lic_svc.verify_license_now()
    
    status_doc = await db.system_settings.find_one({"_id": "license_status"}) or {}
    
    if is_valid:
        return {"message": "License Activated Successfully", "data": status_doc}
    else:
        raise HTTPException(status_code=400, detail=status_doc.get("message", "Invalid License Key"))
