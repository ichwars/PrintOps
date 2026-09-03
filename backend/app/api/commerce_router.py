"""Commercial and warehouse route registration kept out of the application entry point."""

from fastapi import APIRouter

from backend.app.api.routes import (
    business_profiles,
    calculation_projects,
    calculations,
    commercial_documents,
    customers,
    document_configurations,
    document_layouts,
    document_render,
    einvoices,
    equipment,
    lexware,
    lexware_documents,
    offers,
    orders,
    procurement,
    small_parts,
    warehouse_articles,
)

router = APIRouter()
for module in (
    business_profiles,
    document_configurations,
    document_layouts,
    document_render,
    commercial_documents,
    einvoices,
    calculations,
    calculation_projects,
    offers,
    orders,
    customers,
    procurement,
    equipment,
    small_parts,
    warehouse_articles,
    lexware,
    lexware_documents,
):
    router.include_router(module.router)
