import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM = os.environ.get('MAIL_FROM', MAIL_USERNAME)
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'


def _send(to: str, subject: str, html: str, text: str) -> bool:
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.warning("Mail non configuré (MAIL_USERNAME/MAIL_PASSWORD manquants) — email non envoyé à %s", to)
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = MAIL_FROM
    msg['To'] = to
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=10) as server:
            if MAIL_USE_TLS:
                server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM, [to], msg.as_bytes())
        logger.info("Email envoyé à %s", to)
        return True
    except Exception as e:
        logger.error("Erreur envoi email à %s : %s", to, e)
        return False


def send_verification_email(user, token: str, base_url: str) -> bool:
    verify_url = f"{base_url.rstrip('/')}/verify-email/{token}"
    subject = "Confirmez votre adresse email — Wardrobe"

    html = f"""
<html><body style="font-family:sans-serif;color:#333;max-width:480px;margin:auto">
  <h2 style="font-weight:300">Confirmer votre email</h2>
  <p>Bonjour <strong>{user.username}</strong>,</p>
  <p>Cliquez sur le bouton ci-dessous pour activer votre compte :</p>
  <p style="text-align:center;margin:2rem 0">
    <a href="{verify_url}"
       style="background:#111;color:#fff;padding:.75rem 1.5rem;border-radius:6px;text-decoration:none;font-size:.9rem">
      Confirmer mon adresse email
    </a>
  </p>
  <p style="font-size:.8rem;color:#666">Ce lien est valable <strong>24 heures</strong>.</p>
  <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0">
  <p style="font-size:.75rem;color:#999">Wardrobe — votre garde-robe personnelle</p>
</body></html>
"""
    text = (
        f"Bonjour {user.username},\n\n"
        f"Confirmez votre email en visitant ce lien (valable 24 h) :\n{verify_url}"
    )

    return _send(user.email, subject, html, text)


def send_price_alert_email(user, dropped_items: list) -> bool:
    if not dropped_items:
        return False

    rows_html = ''.join(
        f'<tr>'
        f'<td style="padding:.5rem .75rem;border-bottom:1px solid #eee">{it["name"]}</td>'
        f'<td style="padding:.5rem .75rem;border-bottom:1px solid #eee;color:#888;text-decoration:line-through">{it["old_price"]:.2f} {it["currency"]}</td>'
        f'<td style="padding:.5rem .75rem;border-bottom:1px solid #eee;color:#1A6035;font-weight:600">{it["new_price"]:.2f} {it["currency"]}</td>'
        f'</tr>'
        for it in dropped_items
    )
    rows_text = '\n'.join(
        f'- {it["name"]} : {it["old_price"]:.2f} → {it["new_price"]:.2f} {it["currency"]}'
        for it in dropped_items
    )

    subject = f"Baisse de prix sur {len(dropped_items)} article(s) de votre wishlist — Wardrobe"
    html = f"""
<html><body style="font-family:sans-serif;color:#333;max-width:520px;margin:auto">
  <h2 style="font-weight:300">Bonne nouvelle !</h2>
  <p>Bonjour <strong>{user.username}</strong>, des articles de votre liste d'envies ont baissé de prix :</p>
  <table style="width:100%;border-collapse:collapse;margin:1.5rem 0">
    <thead><tr style="background:#f5f5f5">
      <th style="padding:.5rem .75rem;text-align:left">Article</th>
      <th style="padding:.5rem .75rem;text-align:left">Ancien prix</th>
      <th style="padding:.5rem .75rem;text-align:left">Nouveau prix</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="text-align:center">
    <a href="/boutique/wishlist" style="background:#111;color:#fff;padding:.65rem 1.25rem;border-radius:6px;text-decoration:none;font-size:.9rem">Voir ma wishlist</a>
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0">
  <p style="font-size:.75rem;color:#999">Wardrobe — votre garde-robe personnelle</p>
</body></html>
"""
    text = f"Bonjour {user.username},\n\nBaisses de prix sur votre wishlist :\n{rows_text}\n"
    return _send(user.email, subject, html, text)


def send_reset_email(user, token: str, base_url: str) -> bool:
    reset_url = f"{base_url.rstrip('/')}/reset-password/{token}"
    subject = "Réinitialisation de votre mot de passe — Wardrobe"

    html = f"""
<html><body style="font-family:sans-serif;color:#333;max-width:480px;margin:auto">
  <h2 style="font-weight:300">Réinitialisation de mot de passe</h2>
  <p>Bonjour <strong>{user.username}</strong>,</p>
  <p>Vous avez demandé à réinitialiser votre mot de passe. Cliquez sur le bouton ci-dessous :</p>
  <p style="text-align:center;margin:2rem 0">
    <a href="{reset_url}"
       style="background:#111;color:#fff;padding:.75rem 1.5rem;border-radius:6px;text-decoration:none;font-size:.9rem">
      Réinitialiser mon mot de passe
    </a>
  </p>
  <p style="font-size:.8rem;color:#666">Ce lien est valable <strong>1 heure</strong>. Si vous n'avez pas fait cette demande, ignorez cet email.</p>
  <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0">
  <p style="font-size:.75rem;color:#999">Wardrobe — votre garde-robe personnelle</p>
</body></html>
"""
    text = (
        f"Bonjour {user.username},\n\n"
        f"Réinitialisez votre mot de passe en visitant ce lien (valable 1 h) :\n{reset_url}\n\n"
        "Si vous n'avez pas fait cette demande, ignorez cet email."
    )

    return _send(user.email, subject, html, text)


def send_email_change_email(user, new_email: str, token: str, base_url: str) -> bool:
    confirm_url = f"{base_url.rstrip('/')}/confirm-email-change/{token}"
    subject = "Confirmez votre nouvelle adresse email — Wardrobe"

    html = f"""
<html><body style="font-family:sans-serif;color:#333;max-width:480px;margin:auto">
  <h2 style="font-weight:300">Confirmer votre nouvelle adresse email</h2>
  <p>Bonjour <strong>{user.username}</strong>,</p>
  <p>Vous avez demandé à remplacer l'adresse <strong>{user.email}</strong> par <strong>{new_email}</strong>.</p>
  <p>Cliquez sur le bouton ci-dessous pour confirmer ce changement :</p>
  <p style="text-align:center;margin:2rem 0">
    <a href="{confirm_url}"
       style="background:#111;color:#fff;padding:.75rem 1.5rem;border-radius:6px;text-decoration:none;font-size:.9rem">
      Confirmer la nouvelle adresse
    </a>
  </p>
  <p style="font-size:.8rem;color:#666">Ce lien est valable <strong>24 heures</strong>. Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.</p>
  <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0">
  <p style="font-size:.75rem;color:#999">Wardrobe — votre garde-robe personnelle</p>
</body></html>
"""
    text = (
        f"Bonjour {user.username},\n\n"
        f"Vous avez demandé à remplacer {user.email} par {new_email}.\n"
        f"Confirmez ce changement en visitant ce lien (valable 24 h) :\n{confirm_url}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
    )

    return _send(new_email, subject, html, text)
