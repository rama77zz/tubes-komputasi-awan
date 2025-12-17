/**
 * Pipeline CI/CD untuk Aplikasi Flask ke Azure Web App
 * Alur: Checkout -> Build Docker Image -> Login & Push ke ACR -> Deploy ke Azure Web App
 */
pipeline {
    // Jalankan pipeline pada agent manapun yang tersedia
    agent any

    environment {
        // --- KONFIGURASI ACR ---
        // GANTI: Nama lengkap registry Azure kamu (misal: 'myflaskacr.azurecr.io')
        ACR_REGISTRY = "GANTI_DENGAN_NAMA_ACR_KAMU.azurecr.io"
        // GANTI: Nama repository di ACR (biasanya sama dengan nama aplikasi)
        DOCKER_IMAGE_NAME = "flask-invoice"
        // Tag menggunakan nomor build Jenkins untuk identifikasi unik
        DOCKER_TAG = "${env.BUILD_NUMBER}"
        
        // --- ID Kredensial di Jenkins (HARUS SAMA dengan yang kamu set) ---
        AZURE_CREDENTIALS_ID = "azure-service-principal" // ID untuk otentikasi ke Azure
        DOCKER_CREDENTIALS_ID = "acr-docker-credentials" // ID untuk login ACR
        
        // --- KONFIGURASI AZURE WEB APP ---
        // GANTI: Nama Resource Group Azure kamu
        AZURE_RESOURCE_GROUP = "NAMA_RESOURCE_GROUP_KAMU" 
        // GANTI: Nama Azure Web App kamu
        AZURE_APP_NAME = "web-tiket-brilliant-..." 
    }

    stages {
        stage('Checkout Source Code') {
            steps {
                echo "Mengambil kode dari SCM (GitHub)..."
                // Mengambil kode dari SCM yang terhubung di konfigurasi Job Jenkins
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Building Docker Image: ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG}"
                
                // Menjalankan build menggunakan Dockerfile di root
                // Tagging image dengan nama ACR lengkap
                sh "docker build -t ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG} ."
            }
        }
        
        stage('Docker Login and Push') {
            steps {
                echo "Logging into ACR and Pushing Image..."
                
                // Mengambil username dan password ACR dari Credentials Jenkins
                withCredentials([usernamePassword(credentialsId: env.DOCKER_CREDENTIALS_ID, usernameVariable: 'DOCKER_USERNAME', passwordVariable: 'DOCKER_PASSWORD')]) {
                    
                    // Perintah login Docker ke ACR
                    sh "docker login ${env.ACR_REGISTRY} -u ${DOCKER_USERNAME} -p ${DOCKER_PASSWORD}"
                }
                
                // Melakukan Push (Upload) image ke Azure Container Registry
                sh "docker push ${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}:${env.DOCKER_TAG}"
            }
        }
        
        stage('Deploy to Azure Web App') {
            steps {
                echo "Deploying Image ${env.DOCKER_TAG} to Azure App Service..."
                
                // Menggunakan plugin Azure App Service (Plugin ini wajib diinstal di Jenkins)
                withCredentials([azureServicePrincipal(credentialsId: env.AZURE_CREDENTIALS_ID)]) {
                    
                    // Perintah deployment menggunakan Image terbaru dari ACR
                    azureWebAppPublish azureCredentialsId: env.AZURE_CREDENTIALS_ID, 
                                       resourceGroup: env.AZURE_RESOURCE_GROUP,
                                       appName: env.AZURE_APP_NAME,
                                       imageName: "${env.ACR_REGISTRY}/${env.DOCKER_IMAGE_NAME}", // Nama Image
                                       imageTag: env.DOCKER_TAG, // Tag (versi)
                                       registryUrl: env.ACR_REGISTRY, // Registry URL
                                       // Credentials untuk Web App menarik Image dari ACR
                                       credentialsId: env.DOCKER_CREDENTIALS_ID 
                }
            }
        }
    }
}