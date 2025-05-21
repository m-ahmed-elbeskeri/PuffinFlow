"""Gmail integration for sending and retrieving emails."""

import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import json
from pathlib import Path
import pickle
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

# Configuration paths
CONFIG_DIR = Path.home() / ".flowforge" / "gmail"
TOKENS_FILE = CONFIG_DIR / "token.pickle"

def _get_gmail_service():
    """Get an authenticated Gmail service."""
    creds = None
    
    # Load credentials from file if available
    if TOKENS_FILE.exists():
        with open(TOKENS_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # Check if credentials are expired or missing
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise ValueError("Gmail credentials not found or invalid. Please run setup_oauth first.")
    
    # Build the Gmail service
    return build('gmail', 'v1', credentials=creds)

def send_email(to, subject, body, cc=None, bcc=None, html=False, attachments=None):
    """
    Send an email through Gmail.
    
    Args:
        to: Email recipient(s), comma-separated for multiple
        subject: Email subject line
        body: Email body content
        cc: CC recipient(s), comma-separated for multiple
        bcc: BCC recipient(s), comma-separated for multiple
        html: Whether to send as HTML email
        attachments: List of file paths to attach
        
    Returns:
        Dictionary with message_id, success, and status
    """
    try:
        service = _get_gmail_service()
        
        # Create message
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        
        if cc:
            message['cc'] = cc
        if bcc:
            message['bcc'] = bcc
        
        # Create message content
        if html:
            msg = MIMEText(body, 'html')
        else:
            msg = MIMEText(body, 'plain')
        
        message.attach(msg)
        
        # Add attachments if specified
        if attachments:
            for file_path in attachments:
                path = Path(file_path)
                if path.exists():
                    with open(path, 'rb') as f:
                        part = MIMEApplication(f.read(), Name=path.name)
                    
                    part['Content-Disposition'] = f'attachment; filename="{path.name}"'
                    message.attach(part)
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send message
        result = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        return {
            'message_id': result.get('id', ''),
            'success': True,
            'status': 'Email sent successfully'
        }
        
    except HttpError as error:
        return {
            'message_id': '',
            'success': False,
            'status': f'Error sending email: {str(error)}'
        }
    except Exception as e:
        return {
            'message_id': '',
            'success': False,
            'status': f'Error: {str(e)}'
        }

def get_emails(query="is:unread", max_results=10, include_attachments=False, include_body=True):
    """
    Retrieve emails from Gmail.
    
    Args:
        query: Gmail search query
        max_results: Maximum number of emails to retrieve
        include_attachments: Whether to include attachment information
        include_body: Whether to include the email body
        
    Returns:
        Dictionary with emails and count
    """
    try:
        service = _get_gmail_service()
        
        # Retrieve message list
        result = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = result.get('messages', [])
        email_data = []
        
        for message in messages:
            msg_id = message['id']
            
            # Get message details
            msg = service.users().messages().get(
                userId='me', 
                id=msg_id, 
                format='full' if include_body else 'metadata'
            ).execute()
            
            # Extract headers
            headers = {}
            for header in msg['payload']['headers']:
                headers[header['name'].lower()] = header['value']
            
            # Extract body if requested
            body_text = ""
            if include_body:
                parts = [msg['payload']]
                while parts:
                    part = parts.pop(0)
                    
                    if 'parts' in part:
                        parts.extend(part['parts'])
                    
                    if 'body' in part and 'data' in part['body']:
                        body_data = part['body']['data']
                        body_text += base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')
            
            # Get attachment info if requested
            attachments = []
            if include_attachments:
                parts = [msg['payload']]
                while parts:
                    part = parts.pop(0)
                    
                    if 'parts' in part:
                        parts.extend(part['parts'])
                    
                    if 'filename' in part and part['filename']:
                        attachments.append({
                            'filename': part['filename'],
                            'mime_type': part.get('mimeType', ''),
                            'size': part['body'].get('size', 0) if 'body' in part else 0,
                            'part_id': part['partId'] if 'partId' in part else '',
                        })
            
            # Create email object
            email_obj = {
                'id': msg_id,
                'thread_id': msg['threadId'],
                'subject': headers.get('subject', ''),
                'from': headers.get('from', ''),
                'to': headers.get('to', ''),
                'date': headers.get('date', ''),
                'snippet': msg.get('snippet', ''),
                'labels': msg.get('labelIds', []),
            }
            
            if include_body:
                email_obj['body'] = body_text
                
            if include_attachments:
                email_obj['attachments'] = attachments
            
            email_data.append(email_obj)
        
        return {
            'emails': email_data,
            'count': len(email_data)
        }
        
    except HttpError as error:
        return {
            'emails': [],
            'count': 0,
            'error': str(error)
        }
    except Exception as e:
        return {
            'emails': [],
            'count': 0,
            'error': str(e)
        }

def mark_as_read(message_ids):
    """
    Mark emails as read.
    
    Args:
        message_ids: List of message IDs to mark as read
        
    Returns:
        Dictionary with success and modified_count
    """
    try:
        service = _get_gmail_service()
        
        if isinstance(message_ids, str):
            message_ids = [message_ids]
        
        modified_count = 0
        for msg_id in message_ids:
            # Remove UNREAD label
            service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            modified_count += 1
        
        return {
            'success': True,
            'modified_count': modified_count
        }
        
    except HttpError as error:
        return {
            'success': False,
            'modified_count': 0,
            'error': str(error)
        }
    except Exception as e:
        return {
            'success': False,
            'modified_count': 0,
            'error': str(e)
        }