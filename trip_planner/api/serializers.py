from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=300, trim_whitespace=True)
    finish = serializers.CharField(max_length=300, trim_whitespace=True)

    def validate(self, attrs):
        normalize = lambda value: " ".join(value.casefold().split()).strip(" ,")
        if normalize(attrs["start"]) == normalize(attrs["finish"]):
            raise serializers.ValidationError({"finish": "Start and finish must be different locations."})
        return attrs
