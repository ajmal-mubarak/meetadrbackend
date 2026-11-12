"""
Platform Admin Photo Management Views.
Handles multi-photo upload to Supabase Storage, categorization, and listing.
"""
from rest_framework import views, status, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from apps.accounts.permissions import IsPlatformAdmin
from apps.importers.storage_service import upload_photo, list_photos, delete_photo

class AdminPhotoListView(views.APIView):
    """
    List photos in Supabase Storage by category.
    GET /api/v1/admin/photos/?category=doctors|hospitals|logos
    """
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        category = request.query_params.get('category', 'doctors')
        limit = int(request.query_params.get('limit', 100))
        offset = int(request.query_params.get('offset', 0))

        try:
            photos = list_photos(category=category, limit=limit, offset=offset)
            return Response({
                'success': True,
                'category': category,
                'count': len(photos),
                'photos': photos
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdminPhotoUploadView(views.APIView):
    """
    Upload one or multiple photos to Supabase Storage.
    POST /api/v1/admin/photos/upload/
    Accepts:
    - category: 'doctors' | 'hospitals' | 'logos'
    - files: array of image files (multipart/form-data)
    """
    permission_classes = [IsPlatformAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        category = request.data.get('category', 'doctors')
        files = request.FILES.getlist('files')
        if not files:
            # Fallback to single 'file' parameter
            single_file = request.FILES.get('file')
            if single_file:
                files = [single_file]

        if not files:
            return Response({
                'success': False,
                'error': 'No image files provided for upload.'
            }, status=status.HTTP_400_BAD_REQUEST)

        uploaded = []
        errors = []

        for f in files:
            fname = f.name
            try:
                # Basic size guard (25MB max per image)
                if f.size > 25 * 1024 * 1024:
                    errors.append({'name': fname, 'error': 'File exceeds 25 MB limit.'})
                    continue

                content = f.read()
                content_type = f.content_type
                res = upload_photo(
                    file_bytes=content,
                    filename=fname,
                    category=category,
                    content_type=content_type
                )
                uploaded.append(res)
            except Exception as e:
                errors.append({'name': fname, 'error': str(e)})

        return Response({
            'success': True,
            'category': category,
            'total': len(files),
            'uploaded_count': len(uploaded),
            'uploaded': uploaded,
            'errors': errors
        }, status=status.HTTP_201_CREATED if uploaded else status.HTTP_400_BAD_REQUEST)

class AdminPhotoDeleteView(views.APIView):
    """
    Delete a photo from Supabase Storage.
    DELETE /api/v1/admin/photos/delete/
    Payload: {"path": "doctors/filename.jpg"}
    """
    permission_classes = [IsPlatformAdmin]

    def delete(self, request):
        path = request.data.get('path')
        if not path:
            return Response({'error': 'Photo path is required.'}, status=status.HTTP_400_BAD_REQUEST)

        success = delete_photo(path)
        if success:
            return Response({'success': True, 'message': 'Photo deleted successfully.'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Failed to delete photo.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

