from flask import Flask, request, jsonify, redirect, session, url_for
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required
from marshmallow import Schema, fields, ValidationError
from spotify_integration import create_spotify_oauth, get_spotify_token, refresh_spotify_token, spotify_token_required
import spotipy
from dotenv import load_dotenv
import os
from bson import ObjectId


# Carga variables de entorno
load_dotenv()

app = Flask(__name__)

app.config["MONGO_URI"] = os.getenv('MONGO_URI')
app.config["JWT_SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')
mongo = PyMongo(app)
jwt = JWTManager(app)

# Validacion de datos de usuario
class UserSchema(Schema):
    username = fields.Str(required=True)
    email = fields.Email(required=True)
    password = fields.Str(required=True)

user_schema = UserSchema()

# Error para datos invalidos
@app.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify({"error": e.messages}), 400
    
@app.route('/register', methods=['POST'])
def register_user():
    
    try:
        # Validacion de datos
        data = user_schema.load(request.get_json())

        # Si el usuario ya existe
        existing_user = mongo.db.users.find_one({'email': data['email']})
        if existing_user:
            return jsonify({'message': 'El usuario ya existe'}), 409
        

        # Hasheo de contrasena
        hashed_password = generate_password_hash(data['password'])

        user_data ={
            'username': data['username'], 
            'email': data['email'], 
            'password': hashed_password, 
            'created_at': datetime.now(timezone.utc).isoformat(), 
            'favorites': [], 
            'trivia_scores' : [],
            'profile_picture' : ""
        }

        # Insertar usuario
        result = mongo.db.users.insert_one(user_data)
        response = {
            'id': str(result.inserted_id),  # id del usuario insertado
            'username': data['username'],
            'email': data['email'],
            'created_at' : user_data['created_at']
        }
        return jsonify(response), 201


    except ValidationError as e:
        return handle_validation_error(e)
    

@app.route('/login', methods=['POST'])
def login_user():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': 'Faltan datos'}), 400
    
    # Buscar por email
    user = mongo.db.users.find_one({'email': email})

    if not user or not check_password_hash(user['password'], password):
        return jsonify({'message': 'Credenciales invalidas'}), 401

    # Creacion token con email como identidad
    expires = timedelta(hours=1)
    access_token = create_access_token(identity=email, expires_delta=expires)

    return jsonify({'token': access_token}), 200

# Ruta peotegida para obtener info
@app.route('/profile', methods=['GET'])
@jwt_required()
def user_profile():
    # Obtener identidad del token
    current_user = get_jwt_identity()
    user = mongo.db.users.find_one({'email' : current_user},{'_id':0, 'password': 0})

    if not user:
        return jsonify({'message': 'Usuario no encotrado'}), 404
    
    return jsonify(user), 200

# Errores rutas no encontradas
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Ruta no encotrada"}), 404

# Errores genericos
@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"error": "Error interno del servidor"}), 500


# -------------------------- Spotify ---------------------------


@app.route('/')
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    code = request.args.get('code')

    if code:
        try:
            print(f"Codigo de autorizacion recibido: {code}")
            token_info = sp_oauth.get_access_token(code)
            print(f"Token info: {token_info}")
            session['token_info'] = token_info
            print("Token de Spotify almacenado:", token_info)
            return redirect(url_for('home'))
        except Exception as e:
            return jsonify({"message": f"Error al obtener el token de acceso de Spotify: {str(e)}"}), 400
    else:
        print("Codigo de autorizacion no recibido")
        return jsonify({"message": "Error: No se ha recibido el código de autorización de Spotify"}), 400

@app.route('/home')
def home():
    token_info = get_spotify_token()
    print("Token en /home", token_info)
    if token_info:
        sp_oauth = create_spotify_oauth()
        refresh_spotify_token(sp_oauth)
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user_profile = sp.current_user()
        return f"Bievenido, {user_profile['display_name']}!"
    return "Por favor, inicia sesion"


# --------------------------- Coleccion Album -------------------------

# Crear  album
@app.route('/albums', methods=['POST'])
@jwt_required()
def create_album():
    data = request.get_json()

    # Validacion de datos 
    album_id = data.get('album_id') # El de spotfy
    name = data.get('name')
    artist = data.get('artist')

    if not album_id:
        return jsonify({'message' : 'El album_id es requerido'}), 400
    
    # Crear objeto album con lo esencial
    album_data = {
        'album_id' : album_id,
        'name' : name,
        'artist' : artist,
        'created_at' : datetime.now(timezone.utc).isoformat()
    }

    # Insertar el album en la coleccion
    result = mongo.db.albums.insert_one(album_data)
    
    respose = {
        'id' : str(result.inserted_id),
        'album_id' : album_id,
        'name' : name,
        'artist' : artist,
        'created_at' : album_data['created_at']
    }
    return jsonify(respose), 201

# Lectura de album
@app.route('/search_album', methods=['GET'])
@spotify_token_required
def search_album():
    album_name = request.args.get('name')

    # Obtén el token de Spotify
    token_info = get_spotify_token()
    if token_info is None:
        return jsonify({'error': 'No hay token de Spotify disponible, inicia sesión'}), 401

    # Conecta con la API de Spotify
    sp = spotipy.Spotify(auth=token_info['access_token'])
    
    # Busca el álbum
    results = sp.search(q=album_name, type='album')

    if results['albums']['items']:
        album_data = results['albums']['items'][0]
        album_id = album_data['id']

        # Verifica si el álbum ya está en la base de datos
        existing_album = mongo.db.albums.find_one({'album_id': album_id})
        if not existing_album:
            # Guardar los datos relevantes en la colección
            mongo.db.albums.insert_one({
                'album_id': album_id,
                'name': album_data['name'],
                'artist': [artist['name'] for artist in album_data['artists']],
                'created_at': datetime.now(timezone.utc).isoformat()
            })

        # Buscar comentarios en la colección
        comments = mongo.db.comments.find({'album_id': album_id})
        comments_list = [comment['text'] for comment in comments]

        return jsonify({
            'album_id': album_id,
            'name': album_data['name'],
            'artist': [artist['name'] for artist in album_data['artists']],
            'release_date': album_data['release_date'],  # Fecha de lanzamiento
            'comments': comments_list
        }), 200
    else:
        return jsonify({'error': 'Álbum no encontrado en Spotify'}), 404

# Actualizar album
@app.route('/albums/<string:album_id>', methods=['PUT']) # ID SPOTIFY
@jwt_required()
def update_album(album_id):
    data = request.get_json()

    # Validar datos necesarios
    name = data.get('name')
    artist = data.get('artist')

    # Buscar album en db
    album = mongo.db.albums.find_one({'album_id' : album_id})

    if not album:
        return jsonify({'message' : 'Album no encontrado'}), 404
    
    # Actualizar los campos
    update_data = {}
    if name:
        update_data['name'] = name
    if artist:
        update_data['artist'] = artist
    
    # Actualizar album en la coleccion
    mongo.db.albums.update_one({'album_id' : album_id}, {'$set': update_data})

    return jsonify({'message' : 'Album actualizado exitosamennte'}), 200


# Eliminar album
@app.route('/albums/<string:album_id>', methods=['DELETE']) # ID MONGO
@jwt_required()
def delete_album(album_id):
    # Obteer identidad del usuario
    current_user = get_jwt_identity()

    # Buscar album en db
    album = mongo.db.albums.find_one({'_id': ObjectId(album_id)})

    if not album:
        return jsonify({'message' : 'Album no encontrado'}), 404
    
    # Eliminar album 
    mongo.db.albums.delete_one({'_id' : ObjectId(album_id)})

    return jsonify({'message' : 'Album eliminado exitosamente'}), 200

# ---------------------------- Coleccion canciones ----------------------------

# Creacion cancion
@app.route('/songs', methods=['POST'])
@jwt_required()
def create_songs():
    data = request.get_json()

    # Validacion de datos necesarios
    song_id = data.get('song_id') # De spotify
    name = data.get('name')
    album_id = data.get('album_id')

    if not song_id or not album_id:
        return jsonify({'message' : 'El song_id y el album_id son requeridos'}), 400
    
    song_data = {
        'song_id' : song_id,
        'name' : name,
        'album_id' : album_id,
        'created_at' : datetime.now(timezone.utc).isoformat()
    }

    # Insertar a coleccion
    result = mongo.db.songs.insert_one(song_data)

    response = {
        'id' : str(result.inserted_id),
        'song_id' : song_id,
        'name' : name,
        'album_id' : album_id,
        'created_at' : song_data['created_at']
    }
    return jsonify(response), 201

# Lectura de cancion
@app.route('/search_song', methods=['GET'])
@spotify_token_required
def search_song():
    song_name = request.args.get('name')

    # Obtén el token de Spotify
    token_info = get_spotify_token()
    if token_info is None:
        return jsonify({'error': 'No hay token de Spotify disponible, inicia sesión'}), 401

    # Conecta con la API de Spotify
    sp = spotipy.Spotify(auth=token_info['access_token'])
    
    # Busca la canción
    results = sp.search(q=song_name, type='track')

    if results['tracks']['items']:
        song_data = results['tracks']['items'][0]
        song_id = song_data['id']
        
        # Verifica si la canción ya está en la base de datos
        existing_song = mongo.db.songs.find_one({'song_id': song_id})
        if not existing_song:
            # Guardar los datos relevantes en la colección
            mongo.db.songs.insert_one({
                'song_id': song_id,
                'name': song_data['name'],
                'album_id': song_data['album']['id'],  # Almacena el ID del álbum
                'created_at': datetime.now(timezone.utc).isoformat()
            })

        # Buscar comentarios en la colección
        comments = mongo.db.comments.find({'song_id': song_id})
        comments_list = [comment['text'] for comment in comments]

        return jsonify({
            'song_id': song_id,
            'name': song_data['name'],
            'artist': [artist['name'] for artist in song_data['artists']],
            'album': song_data['album']['name'],  # Nombre del álbum
            'release_date': song_data['album']['release_date'],  # Fecha de lanzamiento
            'comments': comments_list
        }), 200
    else:
        return jsonify({'error': 'Canción no encontrada en Spotify'}), 404

    
# Actualizar
@app.route('/songs/<string:song_id>', methods=['PUT']) # ID SPOTIFY
@jwt_required()
def update_song(song_id):
    data = request.get_json()

    # Validar datos necesarios
    name = data.get('name')
    album_id = data.get('album_id')

    # Buscar cancion en db
    song = mongo.db.songs.find_one({'song_id' : song_id})

    if not song:
        return jsonify({'message': 'Cancion no encontrada'}), 404
    
    # Actualizar los campos
    update_data = {}
    if name:
        update_data['name'] = name
    if album_id:
        update_data['album_id'] = album_id
    
    # Actualizar cancion en la coleccion
    mongo.db.songs.update_one({'song_id': song_id}, {'$set':update_data})
    
    return jsonify({'message' : 'Cancion actualizada exitosamente'}), 200


# Eliminar canciones
@app.route('/songs/<string:song_id>', methods=['DELETE']) # ID MONGO
@jwt_required()
def delete_song(song_id):
    # Obtener la identidad del usuario
    current_user = get_jwt_identity()

    # Buscar la cancion en la base de datos
    song = mongo.db.songs.find_one({'_id': ObjectId(song_id)})

    if not song:
        return jsonify({'message' : 'Cancion no encotrada'}), 404
    
    # Eliminar cancion
    mongo.db.songs.delete_one({'_id': ObjectId(song_id)})

    return jsonify({'message' : 'Cancion eliminada exitosamente'})

# ----------------------- Coleccion comentarios ----------------------

@app.route('/comments', methods=['POST'])
@jwt_required()
def create_comment():
    current_user = get_jwt_identity()

    # Obtener el token de Spotify
    token_info = get_spotify_token()
    print("Token de spotify en comentarios:", token_info)
    if token_info is None:
        return jsonify({'message': 'No se ha podido obtener el token de Spotify, inicia sesión'}), 401

    data = request.get_json()
    album_name = data.get('album_name')
    song_name = data.get('song_name')
    text = data.get('text')

    if not text:
        return jsonify({'message': 'El texto del comentario es requerido'}), 400

    # Asegurarse de que haya al menos una referencia (álbum o canción)
    if not album_name and not song_name:
        return jsonify({'message': 'Se debe especificar un álbum o una canción para el comentario'}), 400

    album_id = None
    song_id = None

    # Buscar el ID del álbum por su nombre
    if album_name:
        album = mongo.db.albums.find_one({'name': album_name})
        if not album:
            sp = spotipy.Spotify(auth=token_info['access_token'])
            results = sp.search(q=album_name, type='album')
            if results['albums']['items']:
                album_id = results['albums']['items'][0]['id']  # Usar el ID de Spotify
            else:
                return jsonify({'message': 'Álbum no encontrado'}), 404
        else:
            album_id = str(album['_id'])    

    # Buscar la canción por su nombre
    if song_name:
        song = mongo.db.songs.find_one({'name': song_name})
        if not song:
            sp = spotipy.Spotify(auth=token_info['access_token'])
            results = sp.search(q=song_name, type='track')
            if results['tracks']['items']:
                song_id = results['tracks']['items'][0]['id']  # Usar el ID de Spotify
            else:
                return jsonify({'message': 'Canción no encontrada'}), 404
        else:
            song_id = str(song['_id'])  

    # Crear el comentario
    comment_data = { 
        'user': current_user,
        'album_id': album_id,
        'song_id': song_id,
        'text': text,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'comment_type' : 'album' if album_id else 'song'
    }
    result = mongo.db.comments.insert_one(comment_data)

    response = {
        'id': str(result.inserted_id),
        'user': current_user,
        'album_id': album_id,
        'song_id': song_id,
        'text': text,
        'created_at': comment_data['created_at']
    }
    
    return jsonify(response), 201



# Editar comentario
@app.route('/comments/<string:comment_id>', methods=['PUT']) # ID MONGO
@jwt_required()
def update_comment(comment_id):
    current_user = get_jwt_identity()
    data = request.get_json()

    # Buscar el comenntario en la base de datos
    comment = mongo.db.comments.find_one({'_id' : ObjectId(comment_id)})

    if not comment:
        return jsonify({'message': 'Comentario no encontrado'}), 404
    
    # Verificar que pertenece al usuario actual
    if comment['user'] != current_user:
        return jsonify({'message' : 'No tienes permiso para modificar'}), 403


    # Actualizar comentario
    new_text = data.get('text')
    if not new_text:
        return jsonify({'message' : 'El texto del comentario es requerido'}), 400 
    
    mongo.db.comments.update_one({'_id' : ObjectId(comment_id)}, {'$set': {'text': new_text}})

    return jsonify({'message' : 'Comentario actualizado exitosamente'}), 200

# Eliminar comentario
@app.route('/comments/<string:comment_id>', methods=['DELETE']) # ID MONGO
@jwt_required()
def delete_comment(comment_id):
    current_user = get_jwt_identity()

    # Buscar el comentario
    comment = mongo.db.comments.find_one({'_id' : ObjectId(comment_id)})

    if not comment:
        return jsonify({'message' : 'Comentario no encontrado'}), 404
    
    # Verificar que el comentario perteece al usuario actual
    if comment['user'] != current_user:
        return jsonify({'message': 'No tienes permiso de edicion'}), 403

    # Eliminar comentario
    mongo.db.comments.delete_one({'_id' : ObjectId(comment_id)})

    return jsonify({'message' : 'Comentario elimiando correctamete'}), 200
    




# --------------------------- Coleccion Playlist ----------------------------

# Creacion de playlist

@app.route('/playlist', methods=['POST'])
@jwt_required()
def create_playlist():
    current_user = get_jwt_identity()
    data = request.get_json()

    # Validar datos necesarios
    name = data.get('name')
    description = data.get('description', "")
    songs = data.get('songs', []) # Lista de song_id de spotify

    if not name:
        return jsonify({'message': 'El nombre de la playlist es requerido'}),400
    
    # Crear la playlist
    playlist_data = {
        'name' : name,
        'description' : description,
        'songs' : songs,
        'user' : current_user,
        'created_at' : datetime.now(timezone.utc).isoformat(),
        'comments' : []
        
    }

    # Insertar en la coleccion 
    result = mongo.db.playlist.insert_one(playlist_data)

    response = {
        'id' : str(result.inserted_id),
        'name' : name,
        'description' : description,
        'songs' : songs,
        'created_at' : playlist_data['created_at']
    }
    return jsonify(response), 201

# Obtener una playlist por su ID DE MONGO
@app.route('/playlist/<string:playlist_id>', methods=['GET']) 
def get_playlist(playlist_id):
    # Buscar en la base de datos
    playlist = mongo.db.playlist.find_one({'_id' : ObjectId(playlist_id)})

    if not playlist:
        return jsonify({'message': 'Playlist no encontrada'}), 404
    
    return jsonify({
        'id' : str(playlist['_id']),
        'name' : playlist['name'],
        'description' : playlist.get('description',''),
        'songs' : playlist['songs'],
        'comments' : playlist['comments'],
        'created_at' : playlist['created_at']
    }), 200

# Actualizar la playlist DE MONGO
@app.route('/playlist/<string:playlist_id>', methods=['PUT'])
@jwt_required()
def update_playlist(playlist_id):
    current_user = get_jwt_identity()
    data = request.get_json()

    # Buscar la playlist
    playlist = mongo.db.playlist.find_one({'_id': ObjectId(playlist_id)})

    if not playlist:
        return jsonify({'message' : 'Playlist no encontrada'}), 404
    
    # Verificar que el usuario le pertenezca la playlist
    if playlist['user'] != current_user:
        return jsonify({'message' : 'No tienes permiso para modificar esta playlist'}), 403
    
    # Actualizar datos necesarios
    update_data = {}

    if 'name' in data:
        update_data['name'] = data['name']
    if 'description' in data:
        update_data['description'] = data['description']
    if 'songs' in data:
        update_data['songs'] = data['songs']

    # Actualizar coleccio
    mongo.db.playlist.update_one({'_id': ObjectId(playlist_id)}, {'$set': update_data})
    return jsonify({'message': 'Playlist actualizada exitosamente'}), 200

# Eliminar una playlist ID MONGO
@app.route('/playlist/<string:playlist_id>', methods=['DELETE'])
@jwt_required()
def delete_playlist(playlist_id):
    current_user = get_jwt_identity()

    # Buscar playlist
    playlist = mongo.db.playlist.find_one({'_id': ObjectId(playlist_id)})

    if not playlist:
        return jsonify({'message': 'Playlist no encontrada'}), 404
    
    # Verificar que el usuario sea el propietario

    if playlist['user'] != current_user:
        return jsonify({'message' : 'No tienes el permiso para eliminar la playlist'}),403
    
    #Elimiar playlist
    mongo.db.playlist.delete_one({'_id': ObjectId(playlist_id)})

    return jsonify({'message': 'Playlist eliminada exitosamente'}), 200


    
# -------------------------- Coleccion trivia --------------------------------

# Crear trivia
@app.route('/trivia', methods=['POST'])
@jwt_required()
def create_trivia():
    current_user = get_jwt_identity()
    data = request.get_json()

    # Validar los campos necesarios
    question = data.get('question')
    options = data.get('options',[]) # Opciones de respuesta
    correct_answer = data.get('correct_answer')

    if not question or not options or not correct_answer:
        return jsonify({'message': 'Faltan datos necesarios para para crear la trivida'}), 400
    
    # Crear el documentos de trivia
    trivia_data = {
        'question' : question,
        'options' : options,
        'correct_answer' : correct_answer,
        'user' : current_user,
        'created_at' : datetime.now(timezone.utc).isoformat(),
        'answer' : [] # Guardado de respuestas
    }

    result = mongo.db.trivia.insert_one(trivia_data)

    response = {
        'id' : str(result.inserted_id),
        'question' : question,
        'options' : options,
        'created_at' : trivia_data['created_at']    
    }
    return jsonify(response), 201

# Obtener trivia por id MONGO
@app.route('/trivia/<string:trivia_id>', methods=['GET']) 
def get_trivia(trivia_id):
    trivia = mongo.db.trivia.find_one({'_id': ObjectId(trivia_id)})

    if not trivia:
        return jsonify({'message' : 'Trivia no encontrada'}), 404
    
    return jsonify({
        'id' : str(trivia['_id']),
        'question' : trivia['question'],
        'options' : trivia['options'],
        'created_at' : trivia['created_at']
    }), 200

# Actualizar trivia ID MONGO
@app.route('/trivia/<string:trivia_id>', methods=['PUT'])
@jwt_required()
def update_trivia(trivia_id):
    current_user = get_jwt_identity()
    data = request.get_json()

    # Buscar trivia
    trivia = mongo.db.trivia.find_one({'_id': ObjectId(trivia_id)})

    if not trivia:
        return jsonify({'message': 'Trivia no encontrada'}), 404
    
    # Verificar si el usuario es el creador
    if trivia['user'] != current_user:
        return jsonify({'message': 'No tienes permiso para modificar'}), 403
    
    # Actualizar los campos necesarios
    update_data = {}
    if 'question' in data:
        update_data['question'] = data['question']
    if 'options' in data:
        update_data['options'] = data['options']
    if 'correct_answer' in data:
        update_data['correct_answer'] = data['correct_answer']

    mongo.db.trivia.update_one({'_id' : ObjectId(trivia_id)}, {'$set': update_data})

    return jsonify({'message' : 'Trivia actualizada correctamente'}), 200

# Eliminar trivia ID MONGO
@app.route('/trivia/<string:trivia_id>', methods=['DELETE'])
@jwt_required()
def delete_trivia(trivia_id):
    current_user = get_jwt_identity()

    # Buscar trivia
    trivia = mongo.db.trivia.find_one({'_id': ObjectId(trivia_id)})

    if not trivia:
        return jsonify({'message' : 'Trivia no encotrada'}), 404
    
    if trivia['user'] != current_user:
        return jsonify({'message' : 'No tienes permiso para eliminar la trivia'}), 403
    
    mongo.db.trivia.delete_one({'_id': ObjectId(trivia_id)})

    return jsonify({'message' : 'Trivia eliminada correctamente'}), 200
    


if __name__ == "__main__": 
    app.run(host='0.0.0.0', debug=True)
