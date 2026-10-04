FROM mcr.microsoft.com/playwright:v1.58.2-noble
USER root
WORKDIR /opt/browsergrid
COPY runtimes/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund && mkdir -p node_modules/@browsergrid
COPY runtimes/runner.cjs runtimes/reporter.cjs ./
COPY packages/browser-sdk ./sdk
RUN ln -s /opt/browsergrid/sdk node_modules/@browsergrid/test && chown -R root:root /opt/browsergrid && chmod -R a-w /opt/browsergrid
USER 1000:1000
WORKDIR /work
CMD ["node", "/opt/browsergrid/runner.cjs"]
