pipeline {
    agent any

    environment {
        // --- KONFIGURASI ---
        ACR_REGISTRY      = "tugasbesarccacr.azurecr.io"
        DOCKER_IMAGE_NAME = "invoiceinaja"
        DOCKER_TAG        = "latest" 
        
        // ID Kredensial yang tadi Anda buat di Langkah 2
        DOCKER_CREDENTIALS_ID = "acr-docker-credentials"
    }

    stages {
        stage('1. Checkout Code') {
            steps {
                cleanWs()
                checkout scm
            }
        }

        stage('2. Build Docker Image') {
            steps {
                echo "Building Image..."
                // Build dengan tag 'latest' agar Azure Web App selalu mengambil yang terbaru
                bat "docker build -t ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG} ."
            }
        }

        stage('3. Push to ACR') {
            steps {
                echo "Login & Push ke Azure Container Registry..."
                withCredentials([usernamePassword(credentialsId: env.DOCKER_CREDENTIALS_ID, 
                                                 usernameVariable: 'DOCKER_USERNAME', 
                                                 passwordVariable: 'DOCKER_PASSWORD')]) {
                    bat """
                        @echo off
                        echo Login ke Docker...
                        echo %DOCKER_PASSWORD%| docker login ${env.ACR_REGISTRY} -u "%DOCKER_USERNAME%" --password-stdin
                        
                        echo Pushing image...
                        docker push ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG}
                    """
                }
            }
        }
    }

    post {
        success {
            echo "✅ SUKSES! Image dikirim ke ACR. Azure Web App akan otomatis update dalam 1-2 menit (Webhook)."
        }
        always {
            bat "docker rmi ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG} || exit 0"
        }
    }
}
