import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import session, jsonify
import time
from functools import wraps

# Autenticacion con spotify
def create_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="user-library-read playlist-read-private user-read-private"
    )

def get_spotify_token():
    token_info = session.get('token_info', {})
    print("Token info:", token_info)
    
    if not token_info or 'access_token' not in token_info or 'refresh_token' not in token_info:
        print("No se encontro un token de spotify valido")
        return None
    
    if token_info['expires_at'] - int(time.time()) < 60:
        print("El token ha expirado, refrescando token ...")
        token_info = refresh_spotify_token(create_spotify_oauth())
        print("Token después de refrescar:", token_info)  # Agregado para verificar
        session['token_info'] = token_info  # Asegúrate de que esta línea esté aquí

    return token_info


def refresh_spotify_token(sp_oauth):
    token_info = session.get('token_info', {})
    try:
        # Refrescar el token de acceso
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info
        print("Token refrescado exitosamente.")
    except Exception as e:
        print(f"Error al refrescar el token: {str(e)}")
        return None

    return token_info

def spotify_token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token_info = get_spotify_token()
        if token_info is None:
            return jsonify({'message' : 'Por favor, inicia sesion en Spotify'}), 401
        
        return f(*args, *kwargs)
    return decorated_function
        


