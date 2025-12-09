"""Shared utilities for Google Earth Engine operations."""

import ee
import json

def validate_geometry(geometry_data):
    """Validate and convert GeoJSON to Earth Engine geometry.
    
    Args:
        geometry_data: GeoJSON geometry object
        
    Returns:
        ee.Geometry: Earth Engine geometry object
        
    Raises:
        ValueError: If geometry is invalid
    """
    try:
        ee_geometry = ee.Geometry(geometry_data)
        return ee_geometry
    except Exception as e:
        raise ValueError(f"Invalid geometry: {str(e)}")

def calculate_area_hectares(geometry):
    """Calculate area of a geometry in hectares.
    
    Args:
        geometry: Earth Engine geometry
        
    Returns:
        float: Area in hectares
    """
    area_m2 = geometry.area().getInfo()
    return area_m2 / 10000

def get_image_collection_stats(image_collection, geometry, scale=30):
    """Calculate statistics for an image collection over a geometry.
    
    Args:
        image_collection: Earth Engine ImageCollection
        geometry: Earth Engine geometry
        scale: Resolution in meters (default: 30)
        
    Returns:
        dict: Statistics dictionary
    """
    stats = image_collection.mean().reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=scale,
        maxPixels=1e9
    ).getInfo()
    return stats

def format_date(date_string):
    """Format date string for Earth Engine.
    
    Args:
        date_string: Date string in YYYY-MM-DD format
        
    Returns:
        str: Formatted date string
    """
    return date_string

def create_error_response(error_message, status_code=500):
    """Create a standardized error response.
    
    Args:
        error_message: Error message string
        status_code: HTTP status code (default: 500)
        
    Returns:
        tuple: (dict, int) Response dictionary and status code
    """
    return {'error': error_message, 'status': 'failed'}, status_code

def create_success_response(data):
    """Create a standardized success response.
    
    Args:
        data: Response data dictionary
        
    Returns:
        dict: Response dictionary with status
    """
    return {**data, 'status': 'success'}
