import requests

def send_push_notification(topic: str=None, message: str=None, title: str = None, priority: int = 3, tags: list = None):
    """
    Sendet eine Push-Benachrichtigung an die ntfy-App.
    
    :param topic: Der Name des ntfy-Themas (Topic). Sollte einzigartig und schwer zu erraten sein.
    :param message: Der eigentliche Text der Benachrichtigung.
    :param title: (Optional) Der Titel der Benachrichtigung.
    :param priority: (Optional) Dringlichkeit von 1 (Min) bis 5 (Max). Standard ist 3.
    :param tags: (Optional) Eine Liste von Emojis oder Tags (z.B. ['warning', 'computer']).
    """
    url = f"https://ntfy.sh/Ylp9nM1K1m6f"
    
    # Header für erweiterte Funktionen vorbereiten
    headers = {
        "Priority": str(priority)
    }
    
    if title:
        headers["Title"] = title
    
    if tags:
        headers["Tags"] = ",".join(tags)
        
    try:
        # Nachricht per POST-Request senden
        response = requests.post(
            url,
            data=message.encode('utf-8'),
            headers=headers
        )
        
         # Prüfen, ob der Request erfolgreich war (Status-Code 200)
        if response.status_code == 200:
            print(f"Erfolgreich gesendet an url: {url}")
            return True
        else:
            print(f"Fehler beim Senden: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        # Netzwerkfehler
        print(f"Netzwerkfehler: {e}")
        return False

# --- ANWENDUNGSBEISPIEL ---
if __name__ == "__main__":

    
    # 1. Eine einfache Nachricht senden
    send_push_notification(
        message="Dein Skript ist erfolgreich durchgelaufen!"
    )
 
    #from pyniryo import *
    #robot = NiryoRobot("10.8.170.41")
    # Check if calibration is needed


    #print(robot.get_hardware_status())
    #print(robot.get_learning_mode())