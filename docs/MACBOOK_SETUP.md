# MacBook Setup

This guide helps move and run TongHeHui on macOS.

## 1. Copy The Project

Recommended:

```bash
git clone <your-repo-url>
cd heshan.net
```

If you are not using Git yet, copy the whole project folder to the MacBook manually.

## 2. Install Required Tools

Install Homebrew first if needed, then install:

```bash
brew install openjdk@17
brew install maven
brew install node
```

## 3. Verify Versions

```bash
java -version
mvn -version
node -v
npm -v
```

Expected:

- Java 17
- Maven installed and available in terminal
- Node.js installed

## 4. Set JAVA_HOME If Needed

If Java 17 is installed but not active:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"
```

If you want it to persist:

```bash
echo 'export JAVA_HOME=$(/usr/libexec/java_home -v 17)' >> ~/.zshrc
echo 'export PATH="$JAVA_HOME/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## 5. Start Backend

```bash
cd backend
mvn spring-boot:run
```

Backend URL:

```text
http://localhost:8080
```

## 6. Start Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## 7. Important Notes

- Do not copy `frontend/node_modules` from Windows to macOS
- Re-run `npm install` on the MacBook
- Do not rely on `backend/target` from Windows
- Rebuild everything locally on macOS
- The project currently uses an in-memory H2 database, so existing test data will not move with the project

## 8. Common Issues

### `mvn: command not found`

Install Maven:

```bash
brew install maven
```

### Wrong Java version

Force Java 17:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
```

### Frontend cannot call backend

Make sure:

- backend is running on `http://localhost:8080`
- frontend is running with `npm run dev`
- `frontend/vite.config.js` still contains the `/api` proxy

### Port already in use

Check running processes or stop the old server before restarting.
