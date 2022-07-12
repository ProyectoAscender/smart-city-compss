# Copyright 2016 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
COMPSS_VERSION = 2.10
PYTHON_VERSION = 3.6
TAG = ${COMPSS_VERSION}-${PYTHON_VERSION}
BUILDER = bscppc/compss:$(COMPSS_VERSION)
PREFIX =  registry.gitlab.bsc.es/ppc-bsc/software/smartcity-compss/
PREFIX2 = bscppc/
IMAGE = smartcity-compss

all: push

image:
	docker build . -f Dockerfile --build-arg ROOT_CONTAINER=$(BUILDER) -t $(PREFIX)$(IMAGE):$(TAG)
	docker image tag $(PREFIX)$(IMAGE):$(TAG) $(PREFIX2)$(IMAGE):$(TAG)

push: image
	docker push $(PREFIX2)$(IMAGE):$(TAG)
#	docker push $(PREFIX)$(IMAGE):$(TAG)

clean:
