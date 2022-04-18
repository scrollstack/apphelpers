import smtplib
import html2text
import os

from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

from converge import settings


def send_email(
        sender, recipients, subject, text=None, html=None,
        attachments=None, images=None, reply_to=None, bcc=None
):
    """
    text: text message. If html is provided and not text, text will be auto generated
    html: html message
    images: list of cid and image paths.
        eg. [('logo', 'images/logo.png'), ('Bruce', 'images/bat.png')]

    sender: can be sender email string e.g. 'foo@example.com' or
    list/tuple sender name and email  ('Foo', 'foo@example.com')

    """
    assert any((text, html)), 'please provide html or text'

    if html and not text:
        text = html2text.html2text(html)

    from_header = sender
    if isinstance(sender, (list, tuple)):
        from_header = formataddr(sender)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_header
    msg['To'] = ', '.join(recipients)

    if bcc:
        msg['bcc'] = ', '.join(bcc)
    if reply_to:
        msg.add_header('reply-to', reply_to)

    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    if html:
        msg.attach(MIMEText(html, 'html', 'utf-8'))
    if images:
        for cid, img in images:
            img_part = MIMEImage(img)
            img_part.add_header('Content-ID', '<' + cid + '>')
            msg.attach(img_part)
    if attachments:
        for file_path in attachments:
            file_name = os.path.basename(file_path)
            file_part = MIMEBase('application', 'octet-stream')
            attachment = open(file_path, 'rb')
            file_part.set_payload((attachment).read())
            encoders.encode_base64(file_part)
            file_part.add_header('Content-Disposition', f'attachment; filename= {file_name}')
            msg.attach(file_part)

    s = smtplib.SMTP(settings.MD_HOST, settings.MD_PORT)
    if settings.MD_USERNAME:
        s.starttls()
        s.login(settings.MD_USERNAME, settings.MD_KEY)

    s.send_message(msg=msg)
    s.quit()
