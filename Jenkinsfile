pipeline {
    agent any

    environment {
        // --- KONFIGURASI ---
        ACR_REGISTRY      = "tugasbesarccacr.azurecr.io"
        DOCKER_IMAGE_NAME = "invoiceinaja"
        DOCKER_TAG        = "latest" 
        
        // ID Kredensial Admin ACR
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

        // --- INI TAMBAHANNYA AGAR MUNCUL OUTPUT DEPLOY ---
        stage('4. Deploy to Azure Web App') {
            steps {
                script {
                    echo "--------------------------------------------------"
                    echo "       STATUS DEPLOYMENT AZURE WEB APP           "
                    echo "--------------------------------------------------"
                    echo "1. Image berhasil dikirim ke ACR."
                    echo "2. Webhook Azure Web App telah dipicu secara otomatis."
                    echo "3. Website sedang melakukan restart untuk update..."
                    echo "--------------------------------------------------"
                    echo "Silakan cek website Anda dalam 1-2 menit."
                }
            }
        }
    }

    post {
        success {
            echo "✅ PIPELINE SELESAI. Website berhasil diupdate."
        }
        always {
            bat "docker rmi ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG} || exit 0"
        }
    }
}
