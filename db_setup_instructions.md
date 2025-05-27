# PostgreSQL Setup Instructions for Image Metadata ETL

This document provides instructions on how to set up a PostgreSQL database using Docker for the `etl.py` script.

## 1. Install Docker

If you don't have Docker installed, please download and install it from the official website: [https://www.docker.com/get-started](https://www.docker.com/get-started)

## 2. Run PostgreSQL using Docker

Open your terminal or command prompt and run the following command to start a PostgreSQL container:

```bash
docker run --name fashion-postgres -e POSTGRES_USER=myuser -e POSTGRES_PASSWORD=mypassword -e POSTGRES_DB=fashion_db -p 5432:5432 -d postgres:13
```

Let's break down this command:
- `docker run`:  The command to create and start a new Docker container.
- `--name fashion-postgres`: Assigns a name (`fashion-postgres`) to your container for easier management.
- `-e POSTGRES_USER=myuser`: Sets the default superuser for the PostgreSQL instance to `myuser`. You can change `myuser` to your preferred username.
- `-e POSTGRES_PASSWORD=mypassword`: Sets the password for the `myuser` to `mypassword`. **Choose a strong password in a real environment.**
- `-e POSTGRES_DB=fashion_db`: Creates a database named `fashion_db` when the container starts. You can change `fashion_db` to your preferred database name.
- `-p 5432:5432`: Maps port `5432` on your host machine to port `5432` in the container. This allows applications running on your host (like `etl.py`) to connect to PostgreSQL running in the container.
- `-d`: Runs the container in detached mode (in the background).
- `postgres:13`: Specifies the Docker image to use. In this case, it's the official PostgreSQL image, version 13. You can choose a different version if needed.

## 3. Set Environment Variables for `etl.py`

The `etl.py` script requires the following environment variables to connect to the database. Set them in your terminal session where you plan to run the script, or add them to a `.env` file if you are using a library like `python-dotenv` (though the current script uses `os.environ.get` directly).

```bash
export DB_HOST="localhost"
export DB_NAME="fashion_db"
export DB_USER="myuser"
export DB_PASSWORD="mypassword"
```

- **DB_HOST**: `localhost` because the database is running in a Docker container with port 5432 mapped to your localhost.
- **DB_NAME**: `fashion_db` (or whatever you set for `POSTGRES_DB`).
- **DB_USER**: `myuser` (or whatever you set for `POSTGRES_USER`).
- **DB_PASSWORD**: `mypassword` (or whatever you set for `POSTGRES_PASSWORD`).

**Note for Windows users:**
Use `set` instead of `export`:
```cmd
set DB_HOST="localhost"
set DB_NAME="fashion_db"
set DB_USER="myuser"
set DB_PASSWORD="mypassword"
```

## 4. Install `psycopg2-binary`

The `etl.py` script requires the `psycopg2-binary` library to interact with PostgreSQL. If you haven't installed it yet, run:

```bash
pip install psycopg2-binary
```
The script `etl.py` also has a check for this.

## 5. Run the ETL Script

Navigate to the directory containing `etl.py` and run it:

```bash
python etl.py
```

The script will:
1. Attempt to connect to the PostgreSQL database using the environment variables.
2. Read `schema.sql` and create the `image_metadata` table if it doesn't exist.
3. Generate metadata for images in the `./images` directory.
4. Insert this metadata into the `image_metadata` table.

## 6. Verify Data in PostgreSQL

You can verify that the table was created and data was populated using `psql` (PostgreSQL's command-line utility).

**Option 1: Connect using Docker exec (recommended)**

This command executes `psql` inside your running PostgreSQL container:

```bash
docker exec -it fashion-postgres psql -U myuser -d fashion_db
```
- `docker exec -it fashion-postgres`: Executes a command (`psql`) in the running container named `fashion-postgres`.
- `psql -U myuser -d fashion_db`: The `psql` command.
  - `-U myuser`: Connects as the user `myuser`.
  - `-d fashion_db`: Connects to the database `fashion_db`.

You will be prompted for the password (`mypassword`).

**Option 2: If you have `psql` installed locally**

Ensure `psql` is installed on your system. Then you can connect directly:
```bash
psql -h localhost -p 5432 -U myuser -d fashion_db
```
You will be prompted for the password (`mypassword`).

**Once connected via `psql`, run these SQL commands:**

1.  **Check if the table exists and view its structure:**
    ```sql
    \dt image_metadata;
    \d image_metadata;
    ```

2.  **Count the number of rows inserted:**
    ```sql
    SELECT COUNT(*) FROM image_metadata;
    ```
    This should show `30` if you used the image generator from the previous step.

3.  **View a few sample rows:**
    ```sql
    SELECT image_id, garment_type, gender, season FROM image_metadata LIMIT 5;
    ```

To exit `psql`, type `\q` and press Enter.

## Troubleshooting

- **Connection Errors:**
    - Ensure the Docker container `fashion-postgres` is running (`docker ps`).
    - Verify the port mapping (`-p 5432:5432`).
    - Double-check that your environment variables (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD) are correctly set and exported in the terminal session where you run `etl.py`.
- **"FATAL: database 'fashion_db' does not exist"**: Make sure you included `-e POSTGRES_DB=fashion_db` in your `docker run` command, or create the database manually after connecting as the `postgres` user.
- **"FATAL: role 'myuser' does not exist"**: Ensure `POSTGRES_USER` in `docker run` matches `DB_USER` environment variable.
- **"FATAL: password authentication failed for user 'myuser'"**: Ensure `POSTGRES_PASSWORD` in `docker run` matches `DB_PASSWORD` environment variable.
- **`psycopg2` import error**: Make sure you have installed `psycopg2-binary` (`pip install psycopg2-binary`).
```
