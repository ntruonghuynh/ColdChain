FROM node:20-alpine
WORKDIR /app/blockchain
COPY blockchain/package.json blockchain/package-lock.json blockchain/hardhat.config.ts blockchain/tsconfig.json ./
RUN npm ci --no-audit --no-fund
COPY blockchain/contracts ./contracts
COPY blockchain/scripts ./scripts
COPY blockchain/test ./test
CMD ["npx", "hardhat", "node", "--hostname", "0.0.0.0"]
