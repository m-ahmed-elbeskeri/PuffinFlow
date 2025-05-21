"""Google Sheets operations module."""

import os
from typing import Dict, List, Any, Optional, Union
import json

# Import the auth module for credentials and service helpers
from . import auth

def read_range(
    spreadsheet_id: str,
    range: str,
    credentials: Optional[Any] = None,
    value_render_option: str = "FORMATTED_VALUE",
    date_time_render_option: str = "FORMATTED_STRING"
) -> Dict[str, Any]:
    """
    Read data from a specified range in a spreadsheet.
    
    Args:
        spreadsheet_id: ID of the spreadsheet (from the URL)
        range: A1 notation of the range to read (e.g., 'Sheet1!A1:D10')
        credentials: Authorized credentials from authenticate step
        value_render_option: How values should be rendered in the output
        date_time_render_option: How dates, times, and durations should be represented
        
    Returns:
        Dict with values and metadata
    """
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Call the Sheets API to get values
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueRenderOption=value_render_option,
            dateTimeRenderOption=date_time_render_option
        ).execute()
        
        # Extract the values from the result
        values = result.get('values', [])
        
        # Calculate metadata
        num_rows = len(values)
        num_columns = max(len(row) for row in values) if values else 0
        
        return {
            "values": values,
            "range": result.get('range', range),
            "num_rows": num_rows,
            "num_columns": num_columns
        }
    except Exception as e:
        return {
            "error": str(e),
            "values": [],
            "range": range,
            "num_rows": 0,
            "num_columns": 0
        }

def write_range(
    spreadsheet_id: str,
    range: str,
    values: List[List[Any]],
    credentials: Optional[Any] = None,
    value_input_option: str = "USER_ENTERED"
) -> Dict[str, Any]:
    """
    Write data to a specified range in a spreadsheet.
    
    Args:
        spreadsheet_id: ID of the spreadsheet (from the URL)
        range: A1 notation of the range to write (e.g., 'Sheet1!A1:D10')
        values: 2D array of values to write to the range
        credentials: Authorized credentials from authenticate step
        value_input_option: How input data should be interpreted
        
    Returns:
        Dict with update metadata
    """
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Prepare the request body
        body = {
            'values': values
        }
        
        # Call the Sheets API to update values
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=value_input_option,
            body=body
        ).execute()
        
        return {
            "updated_range": result.get('updatedRange', range),
            "updated_rows": result.get('updatedRows', 0),
            "updated_columns": result.get('updatedColumns', 0),
            "updated_cells": result.get('updatedCells', 0)
        }
    except Exception as e:
        return {
            "error": str(e),
            "updated_range": range,
            "updated_rows": 0,
            "updated_columns": 0,
            "updated_cells": 0
        }

def append_values(
    spreadsheet_id: str,
    range: str,
    values: List[List[Any]],
    credentials: Optional[Any] = None,
    value_input_option: str = "USER_ENTERED",
    insert_data_option: str = "INSERT_ROWS"
) -> Dict[str, Any]:
    """
    Append values to a spreadsheet.
    
    Args:
        spreadsheet_id: ID of the spreadsheet (from the URL)
        range: A1 notation of the table range (e.g., 'Sheet1!A:D')
        values: 2D array of values to append
        credentials: Authorized credentials from authenticate step
        value_input_option: How input data should be interpreted
        insert_data_option: How the input data should be inserted
        
    Returns:
        Dict with append metadata
    """
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Prepare the request body
        body = {
            'values': values
        }
        
        # Call the Sheets API to append values
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=value_input_option,
            insertDataOption=insert_data_option,
            body=body
        ).execute()
        
        # Extract the updatedRange from the response
        updated_range = result.get('updates', {}).get('updatedRange', range)
        
        return {
            "updated_range": updated_range,
            "updated_rows": result.get('updates', {}).get('updatedRows', 0),
            "updated_columns": result.get('updates', {}).get('updatedColumns', 0),
            "updated_cells": result.get('updates', {}).get('updatedCells', 0)
        }
    except Exception as e:
        return {
            "error": str(e),
            "updated_range": range,
            "updated_rows": 0,
            "updated_columns": 0,
            "updated_cells": 0
        }

def create_spreadsheet(
    title: str,
    sheets: List[str] = None,
    credentials: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Create a new Google Spreadsheet.
    
    Args:
        title: Title of the new spreadsheet
        sheets: List of sheet names to create
        credentials: Authorized credentials from authenticate step
        
    Returns:
        Dict with spreadsheet metadata
    """
    if sheets is None:
        sheets = ["Sheet1"]
    
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Prepare sheet properties
        sheet_properties = [{'properties': {'title': sheet_name}} for sheet_name in sheets]
        
        # Prepare the request body
        body = {
            'properties': {
                'title': title
            },
            'sheets': sheet_properties
        }
        
        # Call the Sheets API to create the spreadsheet
        spreadsheet = service.spreadsheets().create(body=body).execute()
        
        return {
            "spreadsheet_id": spreadsheet.get('spreadsheetId'),
            "spreadsheet_url": spreadsheet.get('spreadsheetUrl'),
            "title": spreadsheet.get('properties', {}).get('title', title)
        }
    except Exception as e:
        return {
            "error": str(e),
            "spreadsheet_id": None,
            "spreadsheet_url": None,
            "title": title
        }

def get_spreadsheet(
    spreadsheet_id: str,
    credentials: Optional[Any] = None,
    include_grid_data: bool = False
) -> Dict[str, Any]:
    """
    Get metadata about a spreadsheet.
    
    Args:
        spreadsheet_id: ID of the spreadsheet (from the URL)
        credentials: Authorized credentials from authenticate step
        include_grid_data: Whether to include grid data in the response
        
    Returns:
        Dict with spreadsheet metadata
    """
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Call the Sheets API to get the spreadsheet
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            includeGridData=include_grid_data
        ).execute()
        
        # Extract sheet metadata
        sheets = []
        for sheet in spreadsheet.get('sheets', []):
            properties = sheet.get('properties', {})
            sheets.append({
                'sheet_id': properties.get('sheetId'),
                'title': properties.get('title'),
                'index': properties.get('index'),
                'row_count': properties.get('gridProperties', {}).get('rowCount'),
                'column_count': properties.get('gridProperties', {}).get('columnCount')
            })
        
        return {
            "properties": spreadsheet.get('properties', {}),
            "sheets": sheets,
            "spreadsheet_url": spreadsheet.get('spreadsheetUrl')
        }
    except Exception as e:
        return {
            "error": str(e),
            "properties": {},
            "sheets": [],
            "spreadsheet_url": None
        }

def list_spreadsheets(
    credentials: Optional[Any] = None,
    max_results: int = 100
) -> Dict[str, Any]:
    """
    List spreadsheets available to the authenticated user.
    
    Args:
        credentials: Authorized credentials from authenticate step
        max_results: Maximum number of spreadsheets to return
        
    Returns:
        Dict with list of spreadsheet metadata
    """
    try:
        # Get the Drive API service (since Sheets API doesn't have a list method)
        service = auth.get_drive_service(credentials)
        
        # Call the Drive API to list spreadsheets
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=max_results,
            fields="files(id, name, createdTime, modifiedTime, webViewLink)"
        ).execute()
        
        spreadsheets = results.get('files', [])
        
        return {
            "spreadsheets": spreadsheets
        }
    except Exception as e:
        return {
            "error": str(e),
            "spreadsheets": []
        }

def format_range(
    spreadsheet_id: str,
    range: str,
    credentials: Optional[Any] = None,
    background_color: Optional[Dict[str, float]] = None,
    text_format: Optional[Dict[str, Any]] = None,
    horizontal_alignment: Optional[str] = None,
    vertical_alignment: Optional[str] = None,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    font_size: Optional[int] = None
) -> Dict[str, Any]:
    """
    Format cells in a specified range.
    
    Args:
        spreadsheet_id: ID of the spreadsheet (from the URL)
        range: A1 notation of the range to format (e.g., 'Sheet1!A1:D10')
        credentials: Authorized credentials from authenticate step
        background_color: RGB color for cell background
        text_format: Text formatting options
        horizontal_alignment: Horizontal alignment of text in cells
        vertical_alignment: Vertical alignment of text in cells
        bold: Whether text should be bold
        italic: Whether text should be italic
        font_size: Font size in points
        
    Returns:
        Dict with formatting result
    """
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Parse the range to get sheet ID and grid range
        # First, get spreadsheet info to find the sheet ID
        spreadsheet_info = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        
        # Extract sheet name from range
        if '!' in range:
            sheet_name = range.split('!')[0].replace("'", "")
        else:
            sheet_name = spreadsheet_info['sheets'][0]['properties']['title']
        
        # Find the sheet ID
        sheet_id = None
        for sheet in spreadsheet_info['sheets']:
            if sheet['properties']['title'] == sheet_name:
                sheet_id = sheet['properties']['sheetId']
                break
        
        if sheet_id is None:
            return {
                "error": f"Sheet '{sheet_name}' not found",
                "updated_range": range,
                "updated_cells": 0
            }
        
        # Convert A1 notation to grid range
        grid_range = {
            'sheetId': sheet_id
        }
        
        # Remove sheet name from range if present
        if '!' in range:
            cell_range = range.split('!')[1]
        else:
            cell_range = range
        
        # If the range is a single cell like 'A1', we need to set start and end row/column
        if ':' not in cell_range:
            # Parse out the row and column from A1 notation
            col_str = ''
            row_str = ''
            for char in cell_range:
                if char.isalpha():
                    col_str += char
                else:
                    row_str += char
            
            # Convert column letters to zero-based index
            col_index = 0
            for char in col_str.upper():
                col_index = col_index * 26 + (ord(char) - ord('A') + 1)
            col_index -= 1  # Make zero-based
            
            row_index = int(row_str) - 1  # Convert to zero-based
            
            grid_range.update({
                'startRowIndex': row_index,
                'endRowIndex': row_index + 1,
                'startColumnIndex': col_index,
                'endColumnIndex': col_index + 1
            })
        else:
            # For ranges like 'A1:D10', we'd need to convert both ends
            # This is simplified and might not handle all cases
            start, end = cell_range.split(':')
            
            # Parse start cell
            start_col_str = ''
            start_row_str = ''
            for char in start:
                if char.isalpha():
                    start_col_str += char
                else:
                    start_row_str += char
            
            # Parse end cell
            end_col_str = ''
            end_row_str = ''
            for char in end:
                if char.isalpha():
                    end_col_str += char
                else:
                    end_row_str += char
            
            # Convert column letters to zero-based index
            start_col_index = 0
            for char in start_col_str.upper():
                start_col_index = start_col_index * 26 + (ord(char) - ord('A') + 1)
            start_col_index -= 1  # Make zero-based
            
            end_col_index = 0
            for char in end_col_str.upper():
                end_col_index = end_col_index * 26 + (ord(char) - ord('A') + 1)
            end_col_index -= 1  # Make zero-based
            
            # Convert row numbers to zero-based indices
            start_row_index = int(start_row_str) - 1
            end_row_index = int(end_row_str)  # End index is exclusive
            
            grid_range.update({
                'startRowIndex': start_row_index,
                'endRowIndex': end_row_index,
                'startColumnIndex': start_col_index,
                'endColumnIndex': end_col_index + 1  # End index is exclusive
            })
        
        # Prepare cell format
        cell_format = {}
        
        # Set background color if provided
        if background_color:
            cell_format['backgroundColor'] = background_color
        
        # Set text format options
        if any([text_format, bold, italic, font_size]):
            text_format_obj = text_format or {}
            
            if bold is not None:
                text_format_obj['bold'] = bold
            
            if italic is not None:
                text_format_obj['italic'] = italic
            
            if font_size is not None:
                text_format_obj['fontSize'] = font_size
            
            cell_format['textFormat'] = text_format_obj
        
        # Set horizontal alignment if provided
        if horizontal_alignment:
            cell_format['horizontalAlignment'] = horizontal_alignment
        
        # Set vertical alignment if provided
        if vertical_alignment:
            cell_format['verticalAlignment'] = vertical_alignment
        
        # Prepare the request
        requests = [{
            'repeatCell': {
                'range': grid_range,
                'cell': {
                    'userEnteredFormat': cell_format
                },
                'fields': 'userEnteredFormat'
            }
        }]
        
        # Call the Sheets API to apply formatting
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        
        # Estimate the number of cells updated
        cell_count = (grid_range.get('endRowIndex', 0) - grid_range.get('startRowIndex', 0)) * \
                     (grid_range.get('endColumnIndex', 0) - grid_range.get('startColumnIndex', 0))
        
        return {
            "updated_range": range,
            "updated_cells": cell_count
        }
    except Exception as e:
        return {
            "error": str(e),
            "updated_range": range,
            "updated_cells": 0
        }

def create_sheet(
    spreadsheet_id: str,
    title: str,
    credentials: Optional[Any] = None,
    rows: int = 1000,
    columns: int = 26
) -> Dict[str, Any]:
    """
    Add a new sheet to an existing spreadsheet.
    
    Args:
        spreadsheet_id: ID of the spreadsheet (from the URL)
        title: Title of the new sheet
        credentials: Authorized credentials from authenticate step
        rows: Number of rows in the new sheet
        columns: Number of columns in the new sheet
        
    Returns:
        Dict with sheet creation result
    """
    try:
        # Get the Sheets API service
        service = auth.get_sheets_service(credentials)
        
        # Prepare the request
        requests = [{
            'addSheet': {
                'properties': {
                    'title': title,
                    'gridProperties': {
                        'rowCount': rows,
                        'columnCount': columns
                    }
                }
            }
        }]
        
        # Call the Sheets API to add the sheet
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        
        # Extract the created sheet's ID and properties
        created_sheet = response.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        
        return {
            "sheet_id": created_sheet.get('sheetId'),
            "title": created_sheet.get('title')
        }
    except Exception as e:
        return {
            "error": str(e),
            "sheet_id": None,
            "title": title
        }