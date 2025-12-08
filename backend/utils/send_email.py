import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_evaluation_email(recipient_email: str, candidate_resume: str, evaluation_report: str, session_id: str) -> bool:
    """
    Sends the evaluation email to HR with decision buttons.
    """
    
    # Get SMTP settings
    email_host = os.getenv("EMAIL_HOST")
    email_port = int(os.getenv("EMAIL_PORT", 587))
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")

    if not all([email_host, email_port, email_user, email_pass]):
        print("Email configuration is missing. Skipping email.")
        return False
        
    # --- 2. GENERATE LINKS & BUTTONS ---
    # Define base URL (Use your ngrok url or cloud url in production)
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    print("recipient_email:",recipient_email)
    print(f"email_pass: {email_pass},{email_host},{email_port},{email_user},")
    
    hire_link = f"{api_base_url}/hr-decision?session_id={session_id}&decision=hired"
    reject_link = f"{api_base_url}/hr-decision?session_id={session_id}&decision=rejected"

    buttons_html = f"""
    <div style="margin-top: 30px; padding: 20px; background-color: #f0f8ff; border: 1px solid #b0c4de; border-radius: 8px; text-align: center;">
        <h3 style="margin-top: 0;">HR Decision Required</h3>
        <p style="margin-bottom: 20px;">Based on this report, do you want to proceed with this candidate?</p>
        
        <a href="{hire_link}" style="background-color: #28a745; color: white; padding: 12px 24px; text-decoration: none; margin-right: 15px; border-radius: 5px; font-weight: bold;">
            ✅ Select Candidate
        </a>
        
        <a href="{reject_link}" style="background-color: #dc3545; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
            ❌ Reject Candidate
        </a>
        
        <p style="font-size: 12px; color: #666; margin-top: 15px;">
            Clicking above will immediately email the candidate with the result.
        </p>
    </div>
    """
   
    subject = "AI Interview Evaluation Report - Action Required"
    sender_email = email_user
    
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = recipient_email.strip()
    
    # --- 3. INJECT BUTTONS INTO HTML BODY ---
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #2c3e50; }}
            h3 {{ color: #34495e; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
            pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; border: 1px solid #e9ecef; white-space: pre-wrap; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>AI Interview Evaluation Complete</h2>
            
            <h3>Evaluation Report</h3>
            <div style="background-color: #fff; padding: 10px;">
                {evaluation_report.replace('**', '<b>').replace('**', '</b>').replace('\n', '<br>')}
            </div>
            
            <h3>Candidate Resume (Snippet)</h3>
            <pre>{candidate_resume[:1000]}...</pre>
            
            {buttons_html}
            
            <p style="font-size: 12px; color: #888; text-align: center; margin-top: 30px;">
                This is an automated report from the AI Interview Agent.
            </p>
        </div>
    </body>
    </html>
    """
    
    message.attach(MIMEText(html_body, "html"))
    print(f"Sending evaluation email to {recipient_email}...")
    try:
        with smtplib.SMTP(email_host, email_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(sender_email, recipient_email, message.as_string())
        print(f"Email successfully sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_candidate_result_email(recipient_email: str, decision: str) -> bool:
    """
    Sends an email to the candidate based on the HR's decision.
    
    Args:
        recipient_email (str): The candidate's extracted email.
        decision (str): Either 'hired' or 'rejected'.
    """
    
    # Get SMTP settings from environment variables (Same as your base function)
    email_host = os.getenv("EMAIL_HOST")
    email_port = int(os.getenv("EMAIL_PORT", 587))
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")

    if not all([email_host, email_port, email_user, email_pass]):
        print("Email configuration is missing. Skipping candidate email.")
        return False
        
    sender_email = email_user
    
    # --- 1. Determine Content based on Decision ---
    clean_decision = decision.strip().lower()
    
    if clean_decision == "hired":
        subject = "Update on your Interview Application - Next Steps"
        # You can customize this text
        email_content = f"""
        <h2 style="color: #2e7d32;">Congratulations!</h2>
        <p>Dear Candidate,</p>
        <p>We are pleased to inform you that based on your recent AI interview, our team was impressed with your skills and experience.</p>
        <p><strong>We would like to move forward with your application.</strong></p>
        <p>Our HR team will reach out to you shortly to discuss the next steps and schedule a final discussion.</p>
        <p>Best regards,<br>Recruitment Team</p>
        """
    else:
        subject = "Update on your Job Application"
        email_content = f"""
        <h2 style="color: #333;">Application Update</h2>
        <p>Dear Candidate,</p>
        <p>Thank you for taking the time to complete our AI interview process. We appreciate the effort you put into showcasing your skills.</p>
        <p>After careful review, <strong>we have decided not to move forward with your application at this time</strong>, as we are looking for a different match for this specific role.</p>
        <p>We will keep your resume on file for future openings.</p>
        <p>Best regards,<br>Recruitment Team</p>
        """

    # --- 2. Construct Email ---
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = recipient_email
    
    # HTML Styling
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ padding: 20px; border: 1px solid #ddd; border-radius: 8px; max-width: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            {email_content}
        </div>
        <p style="font-size: 12px; color: #888; text-align: center; margin-top: 20px;">
            This is an automated message from the AI Interview Agent. Please do not reply directly to this email.

        </p>
    </body>
    </html>
    """
    
    message.attach(MIMEText(html_body, "html"))
    
    # --- 3. Send Email ---
    try:
        with smtplib.SMTP(email_host, email_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(sender_email, recipient_email, message.as_string())
        print(f"✅ Result email ({clean_decision}) successfully sent to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending candidate email: {e}")
        return False