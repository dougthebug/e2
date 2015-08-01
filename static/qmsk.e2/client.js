/* Config */
var server = document.location.hostname;
var apiPort = parseInt(document.location.port);
var wsPort = apiPort + 1;

var backendUrl = 'http://' + server + ':' + apiPort + '/api/v1/';
var websocketUrl = 'ws://' + server + ':' + wsPort + '';

/* Angular application */
var e2client = angular.module('e2client', [
	'ngRoute',
	'ngWebsocket',
	'ui.bootstrap'
]);


e2client.config(['$routeProvider', function($routeProvider) {
	$routeProvider.
		when('/presets', {
			templateUrl: 'qmsk.e2/presets.html',
			controller: 'PresetsCtrl',
		}).
		when('/sources', {
			templateUrl: 'qmsk.e2/sources.html',
			controller: 'SourceCtrl',
		}).
		otherwise({
			redirectTo: '/presets',
		});

}]);

e2client.run(function ($rootScope) {
	$rootScope.status = [];
	$rootScope.log = function (msg, data) {
		console.log(msg, data);
		$rootScope.status.unshift({msg: msg, data: data});
	};
	$rootScope.safe = null;
});

e2client.controller('HeaderCtrl', function ($rootScope, $scope, $location) {
	$rootScope.server = server;
	$rootScope.safe = null;

	$scope.isActive = function (location) {
		return location == $location.path();
	}
});

e2client.controller('PresetsCtrl', function ($rootScope, $scope, $http, $websocket) {
	$scope.data = null;
	$scope.seq = 0;

	$scope.collapsedGroups = {};
	
	// Websocket
	var ws = $websocket.$new({
		url: websocketUrl,
		reconnect: true,

		// workaround https://github.com/wilk/ng-websocket/issues/11
		protocols: []
	});

	ws.$on('$open', function () {
		$scope.log('websocket opened');
		ws.$emit('ping', 'hello');
		$scope.loadPresets(); // reload to get current seq
	});

	ws.$on('$message', function (data) {
		$scope.log('websocket message', data);
		$scope.loadPresets();
	});

	ws.$on('$close', function () {
		$scope.log('websocket closed');
	});
	
	// Presets
	$scope.loadPresets = function() {
		$scope.log("presets load");

		$http.get(backendUrl)
			.success(function(data) {
				$scope.log("presets update", {seq: data.seq, presets_length: Object.keys(data.presets).length});
				$scope.data = data;
				$rootScope.safe = data.safe;
				$scope.seq = data.seq;
			}).error(function(err) {
				$scope.log('presets error', err);
			});
	};

	$scope.clickPreset = function(id) {
		$scope.log("preset click", {id: id, seq: $scope.seq});

		$http.post(backendUrl + 'preset/' + id, {seq: $scope.seq})
			.success(function(data) {
				$scope.log('preset success', data);
				$scope.seq = data.seq;
			}).error(function(err) {
				$scope.log('preset error', err);
				$scope.loadPresets(); // reload to get current seq
			});
		return false;
	};
	
	// Commands
	$scope.autotrans = function() {
		return $scope.setInPgm({autotrans: true});
	}

	$scope.cut = function() {
		return $scope.setInPgm({cut: true});
	}

	$scope.setInPgm = function(data) {
		data.seq = $scope.seq;
		
		$scope.log("transition click", data);

		$http.post(backendUrl + 'preset/', data)
			.success(function(data) {
				$scope.log('transition success', data);
				$scope.seq = data.seq;
			}).error(function(err) {
				$scope.log('transition error');
				$scope.loadPresets(); // reload to get current seq
			});
		return false;
	}

	// Initialize
	$scope.loadPresets();
});

e2client.controller('SourceCtrl', function ($rootScope, $scope, $http) {
	$http.get(backendUrl + 'sources/')
		.success(function(data) {
			$rootScope.safe = data.safe;
			$scope.sources = data.sources;
		});
});

e2client.controller('StatusCtrl', function ($rootScope) {

});
