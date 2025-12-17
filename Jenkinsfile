/**
 * Pipeline CI/CD untuk Aplikasi Flask ke Azure Web App (invoiceinaja)
 * MENGGUNAKAN SINTAKS BAT (WINDOWS)
 */
pipeline {
    agent any

    environment {
        // --- KONFIGURASI ACR ---
        ACR_REGISTRY      = "tugasbesarccacr.azurecr.io"
        DOCKER_IMAGE_NAME = "invoiceinaja"
        DOCKER_TAG        = "${env.BUILD_NUMBER}"

        // --- ID Kredensial di Jenkins ---
        AZURE_CREDENTIALS_ID  = "azure-service-principal"
        DOCKER_CREDENTIALS_ID = "acr-docker-credentials"

        // --- KONFIGURASI AZURE WEB APP ---
        AZURE_RESOURCE_GROUP = "tugas-besar_cc"
        AZURE_APP_NAME       = "invoiceinaja"
    }

    stages {
        stage('Checkout Source Code') {
            steps {
                echo "Mengambil kode dari SCM (GitHub)..."
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Building Docker Image: ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG}"
                // MENGGANTI sh MENJADI bat (Menggunakan ^ untuk line continuation)
                bat """
                    docker build ^
                     -t ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG} .
                """
            }
        }

        stage('Docker Login and Push') {
            steps {
                echo "Login ke ACR dan push image..."
                withCredentials([usernamePassword(credentialsId: env.DOCKER_CREDENTIALS_ID,
                                                 usernameVariable: 'DOCKER_USERNAME',
                                                 passwordVariable: 'DOCKER_PASSWORD')]) {
                    // MENGGANTI sh MENJADI bat
                    bat """
                        ECHO ${DOCKER_PASSWORD} | docker login ${env.ACR_REGISTRY} ^
                          -u "${DOCKER_USERNAME}" --password-stdin
                        docker push ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG}
                    """
                }
            }
        }

        stage('Deploy to Azure Web App') {
            steps {
                echo "Deploy image ${env.DOCKER_TAG} ke Azure Web App ${env.AZURE_APP_NAME}..."

                withCredentials([azureServicePrincipal(credentialsId: env.AZURE_CREDENTIALS_ID)]) {
                    // Command ini adalah Groovy/Jenkins DSL, jadi tidak perlu diubah ke bat
                    azureWebAppPublish azureCredentialsId: env.AZURE_CREDENTIALS_ID,
                                         resourceGroup:    env.AZURE_RESOURCE_GROUP,
                                         appName:          env.AZURE_APP_NAME,
                                         dockerImageName:    "${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}",
                                         dockerImageTag:     env.DOCKER_TAG,
                                         dockerRegistryEndpoint: env.ACR_REGISTRY
                }
            }
        }
    }
}
