pipeline {
    agent any

    options {
        timestamps()
        ansiColor('xterm')
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    parameters {
        choice(name: 'ENVIRONMENT', choices: ['staging', 'production'], description: 'Deployment target')
        booleanParam(name: 'RUN_SECURITY_SCAN', defaultValue: true, description: 'Run Trivy and Bandit')
        booleanParam(name: 'SKIP_TESTS', defaultValue: false, description: 'Emergency hotfix only')
    }

    environment {
        PYTHON_VERSION   = '3.12'
        IMAGE_BACKEND    = "cloudops-sentinel-backend:${env.BUILD_NUMBER}"
        IMAGE_FRONTEND   = "cloudops-sentinel-frontend:${env.BUILD_NUMBER}"
        // Credentials are injected by withCredentials at point of use only.
        TRIVY_SEVERITY   = 'CRITICAL,HIGH'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git rev-parse --short HEAD > .git-sha'
                script {
                    env.GIT_SHA = readFile('.git-sha').trim()
                    currentBuild.description = "${env.ENVIRONMENT} - ${env.GIT_SHA}"
                }
            }
        }

        stage('Backend build') {
            steps {
                dir('backend') {
                    sh """
                        python3 -m venv .venv
                        . .venv/bin/activate
                        pip install --upgrade pip
                        pip install -r requirements.txt -r requirements-dev.txt
                    """
                }
            }
        }

        stage('Lint') {
            steps {
                dir('backend') {
                    sh '. .venv/bin/activate && ruff check app tests --output-format=concise'
                }
            }
        }

        stage('Test') {
            when { expression { !params.SKIP_TESTS } }
            steps {
                dir('backend') {
                    sh """
                        . .venv/bin/activate
                        export DATABASE_URL=sqlite:///./jenkins.db
                        export ENABLE_SCHEDULER=false
                        export SECRET_KEY=jenkins-ci-only-secret
                        pytest -q --junitxml=reports/junit.xml
                    """
                }
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'backend/reports/junit.xml'
                }
            }
        }

        stage('Frontend build') {
            steps {
                dir('frontend') {
                    sh 'npm ci --no-audit --no-fund'
                    sh 'npm run build'
                }
            }
        }

        stage('Docker image creation') {
            steps {
                sh """
                    docker build -t ${IMAGE_BACKEND} ./backend
                    docker build -t ${IMAGE_FRONTEND} ./frontend
                """
            }
        }

        stage('Security scan') {
            when { expression { params.RUN_SECURITY_SCAN } }
            steps {
                sh """
                    docker run --rm -v "\$PWD:/src" aquasec/trivy:0.56.2 fs \
                        --severity ${TRIVY_SEVERITY} --ignore-unfixed --exit-code 0 /src/backend
                    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.56.2 image \
                        --severity ${TRIVY_SEVERITY} --ignore-unfixed --exit-code 0 ${IMAGE_BACKEND}
                """
                dir('backend') {
                    sh '. .venv/bin/activate && bandit -r app -ll || true'
                    sh '. .venv/bin/activate && pip-audit -r requirements.txt || true'
                }
            }
        }

        stage('Terraform validate') {
            steps {
                dir('infra/terraform') {
                    sh 'terraform fmt -check -recursive'
                    sh 'terraform init -backend=false -input=false'
                    sh 'terraform validate -no-color'
                }
            }
        }

        stage('Approval') {
            when { expression { params.ENVIRONMENT == 'production' } }
            steps {
                // Blocks until an authorised operator approves in the Jenkins UI.
                timeout(time: 30, unit: 'MINUTES') {
                    input message: "Approve deployment of build ${env.BUILD_NUMBER} to production?",
                          ok: 'Deploy',
                          submitter: 'cloudops-admins'
                }
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([
                    file(credentialsId: 'kubeconfig-sentinel', variable: 'KUBECONFIG'),
                    usernamePassword(credentialsId: 'registry-sentinel', usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')
                ]) {
                    sh '''
                        set -eu
                        echo "$REG_PASS" | docker login -u "$REG_USER" --password-stdin "$REGISTRY"
                        docker tag "$IMAGE_BACKEND" "$REGISTRY/$IMAGE_BACKEND"
                        docker tag "$IMAGE_FRONTEND" "$REGISTRY/$IMAGE_FRONTEND"
                        docker push "$REGISTRY/$IMAGE_BACKEND"
                        docker push "$REGISTRY/$IMAGE_FRONTEND"

                        kubectl -n cloudops-sentinel set image deployment/sentinel-backend backend="$REGISTRY/$IMAGE_BACKEND"
                        kubectl -n cloudops-sentinel set image deployment/sentinel-frontend frontend="$REGISTRY/$IMAGE_FRONTEND"
                        kubectl -n cloudops-sentinel rollout status deployment/sentinel-backend --timeout=240s
                        kubectl -n cloudops-sentinel rollout status deployment/sentinel-frontend --timeout=240s
                    '''
                }
            }
        }

        stage('Smoke test') {
            steps {
                withCredentials([string(credentialsId: 'sentinel-health-url', variable: 'HEALTH_URL')]) {
                    sh '''
                        for attempt in 1 2 3 4 5; do
                          if curl -fsS "$HEALTH_URL" | grep -q '"status":"ok"'; then
                            echo "Health check passed"
                            exit 0
                          fi
                          sleep 10
                        done
                        echo "Health check failed" >&2
                        exit 1
                    '''
                }
            }
        }
    }

    post {
        success {
            echo "Build ${env.BUILD_NUMBER} deployed to ${env.ENVIRONMENT}"
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed - check archived logs"
        }
        always {
            archiveArtifacts artifacts: 'backend/reports/**', allowEmptyArchive: true
            cleanWs()
        }
    }
}
