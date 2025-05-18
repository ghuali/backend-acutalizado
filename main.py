from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import bcrypt
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Conexión a PostgreSQL
def conectar():
    return psycopg2.connect(
        host="localhost",
        port="5432",
        database="EsportsCanarias",
        user="postgres",
        password="1234"
    )

# Ejecutar SQL y devolver JSON
def ejecutar_sql(sql):
    try:
        conn = conectar()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql)

        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(rows)
        else:
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"msg": "Operación exitosa"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/usuario/login', methods=['POST'])
def login_usuario():
    data = request.json
    email = data['email']
    contraseña_plana = data['contraseña']

    # Buscar el usuario por email
    sql = f'''SELECT * FROM "Usuario" WHERE email = '{email}' '''
    result = ejecutar_sql(sql)

    if result.status_code != 200 or not result.json:
        return jsonify({"msg": "Credenciales inválidas"}), 401

    usuario = result.json[0]
    hashed = usuario['contraseña']

    # Verificar la contraseña
    if not bcrypt.checkpw(contraseña_plana.encode('utf-8'), hashed.encode('utf-8')):
        return jsonify({"msg": "Credenciales inválidas"}), 401

    return jsonify({
        "id": usuario["id_usuario"],
        "nombre": usuario["nombre"],
        "rol": usuario["rol"],
        "email": usuario["email"]
    })


@app.route('/usuario/registro', methods=['POST'])
def registrar_usuario():
    data = request.json
    nombre = data['nombre']
    email = data['email']
    contraseña_plana = data['contraseña']

    # Hashear la contraseña
    hashed = bcrypt.hashpw(contraseña_plana.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Rol predeterminado: 'jugador'
    rol = 'jugador'

    sql = f'''
    INSERT INTO "Usuario" (nombre, email, contraseña, rol)
    VALUES ('{nombre}', '{email}', '{hashed}', '{rol}')
    '''
    ejecutar_sql(sql)
    return jsonify({"msg": "Usuario registrado correctamente"})


@app.route('/juegos/equipos', methods=['GET'])
def juegos_por_equipos():
    return ejecutar_sql('''SELECT * FROM "Juego" WHERE es_individual = FALSE''')

@app.route('/torneos/activos', methods=['GET'])
def torneos_activos():
    return ejecutar_sql('''
        SELECT t.id_torneo, t.nombre AS torneo, t.fecha_inicio, t.fecha_fin,
               j.nombre AS juego, e.nombre AS evento, e.tipo, e.año
        FROM "Torneo" t
        INNER JOIN "Juego" j ON t.id_juego = j.id_juego
        INNER JOIN "Evento" e ON t.id_evento = e.id_evento
        WHERE t.fecha_fin >= CURRENT_DATE
        ORDER BY t.fecha_inicio ASC
    ''')

@app.route('/torneo/clasificacion', methods=['GET'])
def clasificacion_torneo():
    torneo_id = request.args.get('id')
    return ejecutar_sql(f'''
        SELECT c.id_clasificacion, c.puntos, c.posicion,
               u.nombre AS usuario, eq.nombre AS equipo
        FROM "Clasificacion" c
        LEFT JOIN "Usuario" u ON c.id_usuario = u.id_usuario
        LEFT JOIN "Equipo" eq ON c.id_equipo = eq.id_equipo
        WHERE c.id_torneo = {torneo_id}
        ORDER BY c.posicion ASC
    ''')

@app.route('/equipo/crear', methods=['POST'])
def crear_equipo():
    data = request.json
    nombre = data['nombre']
    fundador = data['fundador']
    fecha = data['fecha_creacion']
    return ejecutar_sql(f'''
        INSERT INTO "Equipo" (nombre, fundador, fecha_creacion)
        VALUES ('{nombre}', {fundador}, '{fecha}')
    ''')

@app.route('/equipo/unir', methods=['POST'])
def unir_equipo():
    data = request.json
    usuario_id = data['usuario_id']
    equipo_id = data['equipo_id']
    return ejecutar_sql(f'''
        INSERT INTO "UsuarioEquipo" (usuario_id, equipo_id)
        VALUES ({usuario_id}, {equipo_id})
    ''')

@app.route('/torneo/crear', methods=['POST'])
def crear_torneo():
    d = request.json
    return ejecutar_sql(f'''
        INSERT INTO "Torneo" (nombre, fecha_inicio, fecha_fin, ubicacion, id_juego, id_evento)
        VALUES ('{d['nombre']}', '{d['fecha_inicio']}', '{d['fecha_fin']}', '{d['ubicacion']}', {d['id_juego']}, {d['id_evento']})
    ''')

@app.route('/torneo/unir', methods=['POST'])
def unir_torneo():
    d = request.json
    if d['tipo'] == 'equipo':
        return ejecutar_sql(f'''
            INSERT INTO "EquipoTorneo" (equipo_id, torneo_id)
            VALUES ({d['id']}, {d['torneo_id']})
        ''')
    else:
        return ejecutar_sql(f'''
            INSERT INTO "UsuarioTorneo" (usuario_id, torneo_id)
            VALUES ({d['id']}, {d['torneo_id']})
        ''')

@app.route('/torneo/clasificacion', methods=['POST'])
def crear_clasificacion():
    d = request.json
    campos = "id_torneo, puntos, posicion"
    valores = f"{d['id_torneo']}, {d['puntos']}, {d['posicion']}"
    if d['tipo'] == 'equipo':
        campos += ", id_equipo"
        valores += f", {d['id']}"
    else:
        campos += ", id_usuario"
        valores += f", {d['id']}"
    return ejecutar_sql(f'''
        INSERT INTO "Clasificacion" ({campos})
        VALUES ({valores})
    ''')

@app.route('/eventos', methods=['GET'])
def obtener_eventos():
    return ejecutar_sql('''SELECT * FROM "Evento" ORDER BY año DESC, tipo ASC''')

@app.route('/juegos', methods=['GET'])
def obtener_juegos():
    return ejecutar_sql('''SELECT * FROM "Juego" ORDER BY nombre''')

@app.route('/usuario/equipos', methods=['GET'])
def equipos_usuario():
    usuario_id = request.args.get('id')
    return ejecutar_sql(f'''
        SELECT e.id_equipo, e.nombre, e.fecha_creacion
        FROM "Equipo" e
        INNER JOIN "UsuarioEquipo" ue ON ue.equipo_id = e.id_equipo
        WHERE ue.usuario_id = {usuario_id}
    ''')

@app.route('/usuario/torneos', methods=['GET'])
def torneos_usuario():
    usuario_id = request.args.get('id')
    return ejecutar_sql(f'''
        SELECT t.id_torneo, t.nombre, t.fecha_inicio, t.fecha_fin
        FROM "Torneo" t
        INNER JOIN "UsuarioTorneo" ut ON ut.torneo_id = t.id_torneo
        WHERE ut.usuario_id = {usuario_id}
        ORDER BY t.fecha_inicio DESC
    ''')

@app.route('/equipo/torneos', methods=['GET'])
def torneos_equipo():
    equipo_id = request.args.get('id')
    return ejecutar_sql(f'''
        SELECT t.id_torneo, t.nombre, t.fecha_inicio, t.fecha_fin
        FROM "Torneo" t
        INNER JOIN "EquipoTorneo" et ON et.torneo_id = t.id_torneo
        WHERE et.equipo_id = {equipo_id}
        ORDER BY t.fecha_inicio DESC
    ''')

@app.route('/equipo/miembros', methods=['GET'])
def miembros_equipo():
    equipo_id = request.args.get('id')
    return ejecutar_sql(f'''
        SELECT u.id_usuario, u.nombre, u.email
        FROM "Usuario" u
        INNER JOIN "UsuarioEquipo" ue ON ue.usuario_id = u.id_usuario
        WHERE ue.equipo_id = {equipo_id}
    ''')

@app.route('/torneo/participantes', methods=['GET'])
def participantes_torneo():
    torneo_id = request.args.get('id')
    return ejecutar_sql(f'''
        SELECT 'equipo' AS tipo, e.id_equipo AS id, e.nombre
        FROM "Equipo" e
        INNER JOIN "EquipoTorneo" et ON et.equipo_id = e.id_equipo
        WHERE et.torneo_id = {torneo_id}
        UNION
        SELECT 'usuario' AS tipo, u.id_usuario AS id, u.nombre
        FROM "Usuario" u
        INNER JOIN "UsuarioTorneo" ut ON ut.usuario_id = u.id_usuario
        WHERE ut.torneo_id = {torneo_id}
    ''')


if __name__ == '__main__':
    app.run(debug=True)
